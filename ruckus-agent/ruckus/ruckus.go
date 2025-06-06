package ruckus

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"time"

	config "github.com/insightfinder/ruckus-agent/configs"
	"github.com/sirupsen/logrus"
)

func NewService(config config.RuckusConfig) *Service {
	// Create cookie jar to handle session cookies
	jar, err := cookiejar.New(nil)
	if err != nil {
		logrus.Fatalf("Failed to create cookie jar: %v", err)
	}

	// Create HTTP client with SSL verification settings and cookie jar
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: !config.VerifySSL,
		},
	}

	client := &http.Client{
		Transport: tr,
		Timeout:   30 * time.Second,
		Jar:       jar, // Enable cookie handling
	}

	baseURL := fmt.Sprintf("https://%s:%d/wsg/api/public/%s",
		config.ControllerHost, config.ControllerPort, config.APIVersion)

	// maxConcurrent := 20 // Adjust based on controller capacity
	// if config.MaxConcurrentRequests > 0 {
	// 	maxConcurrent = config.MaxConcurrentRequests
	// }

	service := &Service{
		Config:        config,
		HttpClient:    client,
		BaseURL:       baseURL,
		SessionExpiry: 30 * time.Minute,
		// MaxConcurrentRequests: maxConcurrent,
		// RequestSemaphore: make(chan struct{}, maxConcurrent),
	}

	return service
}

func (s *Service) Authenticate() error {
	s.SessionMutex.Lock()
	defer s.SessionMutex.Unlock()

	loginURL := fmt.Sprintf("%s/session", s.BaseURL)
	logrus.Debugf("Authenticating to: %s", loginURL)

	payload := map[string]string{
		"username": s.Config.Username,
		"password": s.Config.Password,
	}

	jsonPayload, _ := json.Marshal(payload)

	resp, err := s.HttpClient.Post(loginURL, "application/json", bytes.NewBuffer(jsonPayload))
	if err != nil {
		return fmt.Errorf("authentication request failed: %v", err)
	}
	defer resp.Body.Close()

	logrus.Debugf("Authentication response status: %d", resp.StatusCode)

	if resp.StatusCode != http.StatusOK {
		// Try to get error details
		var errorResp ErrorResponse
		if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
			return fmt.Errorf("authentication failed (code %d): %s", errorResp.Code, errorResp.Message)
		}
		return fmt.Errorf("authentication failed with status: %d", resp.StatusCode)
	}

	// Parse the authentication response
	var authResp AuthResponse
	if err := json.NewDecoder(resp.Body).Decode(&authResp); err != nil {
		logrus.Warnf("Failed to parse auth response: %v", err)
	} else {
		logrus.Debugf("Controller version: %s", authResp.ControllerVersion)
	}

	// Log cookies received
	for _, cookie := range resp.Cookies() {
		logrus.Debugf("Received cookie: %s=%s", cookie.Name, cookie.Value)
		if cookie.Name == "JSESSIONID" {
			logrus.Debug("JSESSIONID cookie received and stored")
		}
	}

	s.LastAuthTime = time.Now()
	logrus.Debug("Successfully authenticated with Ruckus controller")
	return nil
}

// Check if session needs renewal and renew if necessary
func (s *Service) ensureValidSession() error {
	s.SessionMutex.RLock()
	needsRenewal := time.Since(s.LastAuthTime) > s.SessionExpiry-5*time.Minute // Renew 5 minutes before expiry
	s.SessionMutex.RUnlock()

	if needsRenewal {
		logrus.Debug("Session expiring soon, renewing authentication")
		return s.Authenticate()
	}
	return nil
}

// Execute HTTP request with automatic session renewal
func (s *Service) executeRequest(req *http.Request) (*http.Response, error) {
	// Ensure session is valid
	if err := s.ensureValidSession(); err != nil {
		return nil, fmt.Errorf("failed to ensure valid session: %v", err)
	}

	logrus.Debugf("Making request to: %s", req.URL.String())

	resp, err := s.HttpClient.Do(req)
	if err != nil {
		return nil, err
	}

	logrus.Debugf("Request response status: %d", resp.StatusCode)

	// Check for session expiration errors
	if resp.StatusCode == http.StatusUnauthorized {
		// Read the response body to check for session expiration
		var errorResp ErrorResponse
		bodyBytes := make([]byte, 1024)
		n, _ := resp.Body.Read(bodyBytes)
		resp.Body.Close()

		if json.Unmarshal(bodyBytes[:n], &errorResp) == nil && errorResp.Code == 201 {
			logrus.Warn("Session expired (code 201), renewing authentication")
			if err := s.Authenticate(); err != nil {
				return nil, fmt.Errorf("failed to renew session: %v", err)
			}

			// Retry the original request
			newReq := req.Clone(req.Context())
			logrus.Debug("Retrying request after session renewal")
			return s.HttpClient.Do(newReq)
		}

		// If it's not a session expiration, return the original error
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(bodyBytes[:n]))
	}

	return resp, nil
}

// Health check method to verify connectivity
func (s *Service) HealthCheck() error {
	// Simple test query to verify connectivity
	request := APBulkQueryRequest{
		Filters: []Filter{},
		Page:    1,
		Limit:   1,
	}

	url := fmt.Sprintf("%s/query/ap", s.BaseURL)
	jsonPayload, err := json.Marshal(request)
	if err != nil {
		return fmt.Errorf("health check failed to marshal request: %v", err)
	}

	resp, err := s.post(url, jsonPayload)
	if err != nil {
		return fmt.Errorf("health check request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed with status: %d", resp.StatusCode)
	}

	logrus.Debug("Health check passed")
	return nil
}
