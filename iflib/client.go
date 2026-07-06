// Package iflib provides a reusable Go client for the InsightFinder API.
//
// Initialize a client with New(), then call methods grouped by domain:
// projects, systems, instances, metrics, logs, incidents, dependencies, settings, holidays,
// causal groups, and dependency relations (requires password for session login).
//
// Example:
//
//	c, err := iflib.New("https://app.insightfinder.com", "myuser", "mylicensekey", "mypassword")
//	systems, err := c.ListSystems(ctx)
//	groups, err := c.GetCausalGroups(ctx)
package iflib

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"sync"
	"time"
)

const (
	defaultTimeout       = 30 * time.Second
	defaultRetryTimes    = 3
	defaultRetryInterval = 5 * time.Second
)

// Client is the InsightFinder API client. Create one with New().
type Client struct {
	serverURL     string
	userName      string
	licenseKey    string
	password      string
	httpClient    *http.Client // for key/header-auth endpoints
	sessionClient *http.Client // cookie-jar client for session-auth endpoints
	sessionMu     sync.Mutex
	authenticated bool
	retryTimes    int
	retryInterval time.Duration
}

// Option configures a Client at construction time.
type Option func(*Client)

// WithTimeout sets the per-request HTTP timeout for both HTTP clients (default 30s).
func WithTimeout(d time.Duration) Option {
	return func(c *Client) {
		c.httpClient.Timeout = d
		c.sessionClient.Timeout = d
	}
}

// WithRetry configures retry behaviour (default 3 attempts, 5s interval).
func WithRetry(times int, interval time.Duration) Option {
	return func(c *Client) {
		c.retryTimes = times
		c.retryInterval = interval
	}
}

// WithInsecureSkipVerify disables TLS certificate verification on both HTTP clients.
func WithInsecureSkipVerify() Option {
	return func(c *Client) {
		tlsCfg := &tls.Config{InsecureSkipVerify: true} //nolint:gosec
		if t, ok := c.httpClient.Transport.(*http.Transport); ok {
			t.TLSClientConfig = tlsCfg
		}
		if t, ok := c.sessionClient.Transport.(*http.Transport); ok {
			t.TLSClientConfig = tlsCfg
		}
	}
}

// New creates a new InsightFinder API client.
// password is required for session-based endpoints (causal groups, dependency relations).
func New(serverURL, userName, licenseKey, password string, opts ...Option) (*Client, error) {
	if serverURL == "" {
		return nil, fmt.Errorf("serverURL is required")
	}
	if userName == "" {
		return nil, fmt.Errorf("userName is required")
	}
	if licenseKey == "" {
		return nil, fmt.Errorf("licenseKey is required")
	}

	insecureTLS := &tls.Config{InsecureSkipVerify: true} //nolint:gosec
	jar, _ := cookiejar.New(nil)

	c := &Client{
		serverURL:  strings.TrimRight(serverURL, "/"),
		userName:   userName,
		licenseKey: licenseKey,
		password:   password,
		httpClient: &http.Client{
			Timeout:   defaultTimeout,
			Transport: &http.Transport{TLSClientConfig: insecureTLS},
		},
		sessionClient: &http.Client{
			Timeout:   defaultTimeout,
			Jar:       jar,
			Transport: &http.Transport{TLSClientConfig: insecureTLS},
		},
		retryTimes:    defaultRetryTimes,
		retryInterval: defaultRetryInterval,
	}

	for _, opt := range opts {
		opt(c)
	}
	return c, nil
}

// UserName returns the configured user name.
func (c *Client) UserName() string { return c.userName }

// ServerURL returns the configured server URL.
func (c *Client) ServerURL() string { return c.serverURL }

// decodeJSON is a thin wrapper around json.Unmarshal for use within this package.
func decodeJSON(data []byte, v any) error {
	return json.Unmarshal(data, v)
}

// ─── Key/header-auth helpers ─────────────────────────────────────────────────
//
// Auth map (from Postman collections):
//   doJSON       → X-User-Name + X-API-Key   (most /api/external/v*/ endpoints)
//   doLicenseKey → X-User-Name + X-License-Key (/api/v2/timeline*, /api/external/v1/holiday,
//                                               /api/external/v1/thirdpartysetting,
//                                               /api/v1/metricmetadata-external)
//   doForm       → X-User-Name + X-API-Key + credentials in body
//   doCookie     → X-User-Name + X-License-Key + Cookie: userName=…  (/api/v1/logdedicatedmode)

func (c *Client) doJSON(ctx context.Context, method, path string, body any, params url.Values) ([]byte, int, error) {
	var bodyBytes []byte
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, 0, fmt.Errorf("marshal request body: %w", err)
		}
		bodyBytes = b
	}
	fullURL := c.serverURL + path
	if len(params) > 0 {
		fullURL += "?" + params.Encode()
	}
	return c.doWithRetry(ctx, method, fullURL, bodyBytes, func(req *http.Request) {
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-User-Name", c.userName)
		req.Header.Set("X-API-Key", c.licenseKey)
	})
}

func (c *Client) doLicenseKey(ctx context.Context, method, path string, body any, params url.Values) ([]byte, int, error) {
	var bodyBytes []byte
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, 0, fmt.Errorf("marshal request body: %w", err)
		}
		bodyBytes = b
	}
	fullURL := c.serverURL + path
	if len(params) > 0 {
		fullURL += "?" + params.Encode()
	}
	return c.doWithRetry(ctx, method, fullURL, bodyBytes, func(req *http.Request) {
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-User-Name", c.userName)
		req.Header.Set("X-License-Key", c.licenseKey)
	})
}

func (c *Client) doForm(ctx context.Context, method, path string, formData url.Values) ([]byte, int, error) {
	formData.Set("userName", c.userName)
	formData.Set("licenseKey", c.licenseKey)
	fullURL := c.serverURL + path
	return c.doWithRetry(ctx, method, fullURL, []byte(formData.Encode()), func(req *http.Request) {
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("X-User-Name", c.userName)
		req.Header.Set("X-API-Key", c.licenseKey)
	})
}

func (c *Client) doCookie(ctx context.Context, method, path string, params url.Values) ([]byte, int, error) {
	fullURL := c.serverURL + path
	if len(params) > 0 {
		fullURL += "?" + params.Encode()
	}
	return c.doWithRetry(ctx, method, fullURL, nil, func(req *http.Request) {
		req.Header.Set("X-User-Name", c.userName)
		req.Header.Set("X-License-Key", c.licenseKey)
		req.Header.Set("Cookie", fmt.Sprintf("userName=%s;", c.userName))
	})
}

func (c *Client) doWithRetry(ctx context.Context, method, fullURL string, bodyBytes []byte, setHeaders func(*http.Request)) ([]byte, int, error) {
	var lastErr error
	for attempt := 1; attempt <= c.retryTimes; attempt++ {
		var reqBody io.Reader
		if bodyBytes != nil {
			reqBody = bytes.NewReader(bodyBytes)
		}
		req, err := http.NewRequestWithContext(ctx, method, fullURL, reqBody)
		if err != nil {
			return nil, 0, fmt.Errorf("create request: %w", err)
		}
		setHeaders(req)

		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = err
			if attempt < c.retryTimes {
				select {
				case <-ctx.Done():
					return nil, 0, ctx.Err()
				case <-time.After(c.retryInterval):
				}
			}
			continue
		}
		respBody, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, resp.StatusCode, fmt.Errorf("read response: %w", err)
		}
		return respBody, resp.StatusCode, nil
	}
	return nil, 0, fmt.Errorf("after %d attempts: %w", c.retryTimes, lastErr)
}

// ─── Session-auth helpers ─────────────────────────────────────────────────────
//
// Login: POST /api/v1/login-check  form(userName, password, timezone) → JSESSIONID cookie
// Session requests also need licenseKey as a URL query param.

// Login authenticates against /api/v1/login-check and stores the JSESSIONID cookie.
func (c *Client) Login(ctx context.Context) error {
	if c.password == "" {
		return fmt.Errorf("password is required for session-based API calls")
	}

	form := url.Values{}
	form.Set("userName", c.userName)
	form.Set("password", c.password)
	form.Set("timezone", "default")

	req, err := http.NewRequestWithContext(ctx, "POST", c.serverURL+"/api/v1/login-check", strings.NewReader(form.Encode()))
	if err != nil {
		return fmt.Errorf("create login request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := c.sessionClient.Do(req)
	if err != nil {
		return fmt.Errorf("login request: %w", err)
	}
	io.ReadAll(resp.Body) //nolint:errcheck
	resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("login failed: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ensureSession logs in if not already authenticated. Serializes concurrent callers.
func (c *Client) ensureSession(ctx context.Context) error {
	c.sessionMu.Lock()
	defer c.sessionMu.Unlock()
	if c.authenticated {
		return nil
	}
	if err := c.Login(ctx); err != nil {
		return err
	}
	c.authenticated = true
	return nil
}

// invalidateSession forces re-login on the next session call.
func (c *Client) invalidateSession() {
	c.sessionMu.Lock()
	c.authenticated = false
	c.sessionMu.Unlock()
}

// doSessionGet performs a GET using the JSESSIONID session cookie.
// licenseKey is automatically added as a query param (required by session endpoints).
func (c *Client) doSessionGet(ctx context.Context, path string, params url.Values) ([]byte, int, error) {
	if err := c.ensureSession(ctx); err != nil {
		return nil, 0, err
	}
	body, status, err := c.execSessionGet(ctx, path, params)
	if err != nil {
		return nil, 0, err
	}
	if status == 401 || status == 403 {
		c.invalidateSession()
		if err := c.ensureSession(ctx); err != nil {
			return nil, 0, err
		}
		body, status, err = c.execSessionGet(ctx, path, params)
	}
	return body, status, err
}

func (c *Client) execSessionGet(ctx context.Context, path string, params url.Values) ([]byte, int, error) {
	if params == nil {
		params = url.Values{}
	}
	params.Set("licenseKey", c.licenseKey)
	fullURL := c.serverURL + path + "?" + params.Encode()

	var lastErr error
	for attempt := 1; attempt <= c.retryTimes; attempt++ {
		req, err := http.NewRequestWithContext(ctx, "GET", fullURL, nil)
		if err != nil {
			return nil, 0, fmt.Errorf("create request: %w", err)
		}
		resp, err := c.sessionClient.Do(req)
		if err != nil {
			lastErr = err
			if attempt < c.retryTimes {
				select {
				case <-ctx.Done():
					return nil, 0, ctx.Err()
				case <-time.After(c.retryInterval):
				}
			}
			continue
		}
		respBody, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, resp.StatusCode, fmt.Errorf("read response: %w", err)
		}
		return respBody, resp.StatusCode, nil
	}
	return nil, 0, fmt.Errorf("after %d attempts: %w", c.retryTimes, lastErr)
}

// doSessionMultipart performs a multipart/form-data POST using the JSESSIONID session cookie.
// The JSON payload is sent as a file field named "data" with content-type application/json.
// licenseKey is automatically added as a query param.
func (c *Client) doSessionMultipart(ctx context.Context, path string, params url.Values, jsonPayload []byte) ([]byte, int, error) {
	if err := c.ensureSession(ctx); err != nil {
		return nil, 0, err
	}
	body, status, err := c.execSessionMultipart(ctx, path, params, jsonPayload)
	if err != nil {
		return nil, 0, err
	}
	if status == 401 || status == 403 {
		c.invalidateSession()
		if err := c.ensureSession(ctx); err != nil {
			return nil, 0, err
		}
		body, status, err = c.execSessionMultipart(ctx, path, params, jsonPayload)
	}
	return body, status, err
}

func (c *Client) execSessionMultipart(ctx context.Context, path string, params url.Values, jsonPayload []byte) ([]byte, int, error) {
	if params == nil {
		params = url.Values{}
	}
	params.Set("licenseKey", c.licenseKey)
	fullURL := c.serverURL + path + "?" + params.Encode()

	var buf bytes.Buffer
	w := multipart.NewWriter(&buf)
	part, err := w.CreateFormFile("data", "blob")
	if err != nil {
		return nil, 0, fmt.Errorf("create multipart field: %w", err)
	}
	if _, err := part.Write(jsonPayload); err != nil {
		return nil, 0, fmt.Errorf("write multipart payload: %w", err)
	}
	w.Close()

	var lastErr error
	for attempt := 1; attempt <= c.retryTimes; attempt++ {
		req, err := http.NewRequestWithContext(ctx, "POST", fullURL, bytes.NewReader(buf.Bytes()))
		if err != nil {
			return nil, 0, fmt.Errorf("create request: %w", err)
		}
		req.Header.Set("Content-Type", w.FormDataContentType())

		resp, err := c.sessionClient.Do(req)
		if err != nil {
			lastErr = err
			if attempt < c.retryTimes {
				select {
				case <-ctx.Done():
					return nil, 0, ctx.Err()
				case <-time.After(c.retryInterval):
				}
			}
			continue
		}
		respBody, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, resp.StatusCode, fmt.Errorf("read response: %w", err)
		}
		return respBody, resp.StatusCode, nil
	}
	return nil, 0, fmt.Errorf("after %d attempts: %w", c.retryTimes, lastErr)
}
