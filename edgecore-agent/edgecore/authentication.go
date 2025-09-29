package edgecore

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/chromedp/chromedp"
	config "github.com/insightfinder/edgecore-agent/configs"
	"github.com/sirupsen/logrus"
)

// AuthService handles EdgeCore authentication
type AuthService struct {
	config    config.EdgeCoreConfig
	authState *config.AuthState
}

// TokenResponse represents Auth0 token endpoint response
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	IDToken      string `json:"id_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
}

// NewAuthService creates a new authentication service
func NewAuthService(cfg config.EdgeCoreConfig) *AuthService {
	return &AuthService{
		config:    cfg,
		authState: &config.AuthState{},
	}
}

// Generate PKCE verifier + challenge
func (a *AuthService) generatePKCE() (string, string) {
	verifierBytes := make([]byte, 32)
	_, _ = rand.Read(verifierBytes)
	verifier := base64.RawURLEncoding.EncodeToString(verifierBytes)

	h := sha256.New()
	h.Write([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(h.Sum(nil))

	return verifier, challenge
}

// Authenticate performs the full authentication flow with retry mechanism
func (a *AuthService) Authenticate() error {
	for attempt := 1; attempt <= a.config.MaxRetries; attempt++ {
		logrus.Infof("Authentication attempt %d/%d", attempt, a.config.MaxRetries)

		err := a.performLogin()
		if err == nil {
			logrus.Info("Authentication successful")
			return nil
		}

		logrus.Warnf("Authentication attempt %d failed: %v", attempt, err)
		if attempt < a.config.MaxRetries {
			time.Sleep(2 * time.Second) // Wait before retry
		}
	}

	return fmt.Errorf("authentication failed after %d attempts", a.config.MaxRetries)
}

// performLogin performs the actual login flow
func (a *AuthService) performLogin() error {
	verifier, challenge := a.generatePKCE()
	state := "RANDOMSTATE123" // can be anything random

	// Step 1: Build /authorize URL with proper audience and scopes for API access
	authURL := fmt.Sprintf("https://%s/authorize?response_type=code&client_id=%s&redirect_uri=%s&scope=openid%%20profile%%20email%%20read:current_user%%20offline_access&audience=https://netexperience-prod.us.auth0.com/api/v2/&code_challenge=%s&code_challenge_method=S256&state=%s",
		a.config.Auth0Domain, a.config.ClientID, url.QueryEscape(a.config.RedirectURI), challenge, state)

	// Step 2: Use chromedp to login and capture redirect URL
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var finalURL string
	err := chromedp.Run(ctx,
		chromedp.Navigate(authURL),
		chromedp.WaitVisible(`#username`, chromedp.ByID),
		chromedp.SendKeys(`#username`, a.config.Username, chromedp.ByID),
		chromedp.SendKeys(`#password`, a.config.Password, chromedp.ByID),
		chromedp.Click(`button[type=submit]`),
	)

	if err != nil {
		return fmt.Errorf("chromedp login failed: %v", err)
	}

	// Wait for redirect with polling
	maxWaitTime := 10 * time.Second
	pollInterval := 500 * time.Millisecond
	startTime := time.Now()

	for time.Since(startTime) < maxWaitTime {
		err = chromedp.Run(ctx, chromedp.Location(&finalURL))
		if err != nil {
			return fmt.Errorf("failed to get location: %v", err)
		}

		if strings.Contains(finalURL, "callback") || strings.Contains(finalURL, "code=") {
			logrus.Debugf("Found redirect URL: %s", finalURL)
			break
		}

		time.Sleep(pollInterval)
	}

	// Step 3: Extract ?code=... from redirect URL
	u, err := url.Parse(finalURL)
	if err != nil {
		return fmt.Errorf("failed to parse final URL: %v", err)
	}
	code := u.Query().Get("code")
	if code == "" {
		return fmt.Errorf("no authorization code found in redirect URL: %s", finalURL)
	}

	// Step 4: Exchange code + verifier for tokens
	return a.exchangeCodeForTokens(code, verifier)
}

// exchangeCodeForTokens exchanges authorization code for tokens
func (a *AuthService) exchangeCodeForTokens(code, verifier string) error {
	form := url.Values{}
	form.Set("grant_type", "authorization_code")
	form.Set("client_id", a.config.ClientID)
	form.Set("code", code)
	form.Set("code_verifier", verifier)
	form.Set("redirect_uri", a.config.RedirectURI)
	form.Set("audience", "https://netexperience-prod.us.auth0.com/api/v2/")

	tokenURL := fmt.Sprintf("https://%s/oauth/token", a.config.Auth0Domain)
	logrus.Debugf("Making token request to: %s", tokenURL)

	resp, err := http.PostForm(tokenURL, form)
	if err != nil {
		return fmt.Errorf("token request failed: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != 200 {
		return fmt.Errorf("token request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var tokens TokenResponse
	if err := json.Unmarshal(body, &tokens); err != nil {
		return fmt.Errorf("failed to parse token response: %v", err)
	}

	// Update auth state
	a.authState.AccessToken = tokens.AccessToken
	a.authState.RefreshToken = tokens.RefreshToken
	a.authState.IDToken = tokens.IDToken
	a.authState.ExpiryTime = time.Now().Unix() + int64(tokens.ExpiresIn)
	a.authState.LastRefreshed = time.Now().Unix()

	return nil
}

// RefreshToken refreshes the access token using refresh token with retry mechanism
func (a *AuthService) RefreshToken() error {
	if a.authState.RefreshToken == "" {
		return fmt.Errorf("no refresh token available")
	}

	for attempt := 1; attempt <= a.config.MaxRetries; attempt++ {
		logrus.Infof("Token refresh attempt %d/%d", attempt, a.config.MaxRetries)

		err := a.performTokenRefresh()
		if err == nil {
			logrus.Info("Token refresh successful")
			return nil
		}

		logrus.Warnf("Token refresh attempt %d failed: %v", attempt, err)
		if attempt < a.config.MaxRetries {
			time.Sleep(2 * time.Second) // Wait before retry
		}
	}

	// If all refresh attempts fail, try to re-authenticate
	logrus.Warn("Token refresh failed, attempting re-authentication")
	return a.Authenticate()
}

// performTokenRefresh performs the actual token refresh
func (a *AuthService) performTokenRefresh() error {
	form := url.Values{}
	form.Set("grant_type", "refresh_token")
	form.Set("client_id", a.config.ClientID)
	form.Set("refresh_token", a.authState.RefreshToken)
	form.Set("audience", "https://netexperience-prod.us.auth0.com/api/v2/")

	tokenURL := fmt.Sprintf("https://%s/oauth/token", a.config.Auth0Domain)
	logrus.Debugf("Making refresh token request to: %s", tokenURL)

	resp, err := http.PostForm(tokenURL, form)
	if err != nil {
		return fmt.Errorf("refresh token request failed: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read refresh response body: %v", err)
	}

	if resp.StatusCode != 200 {
		return fmt.Errorf("refresh token request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var tokens TokenResponse
	if err := json.Unmarshal(body, &tokens); err != nil {
		return fmt.Errorf("failed to parse refresh token response: %v", err)
	}

	// Update auth state
	a.authState.AccessToken = tokens.AccessToken
	a.authState.IDToken = tokens.IDToken
	a.authState.ExpiryTime = time.Now().Unix() + int64(tokens.ExpiresIn)
	a.authState.LastRefreshed = time.Now().Unix()

	// Sometimes Auth0 does not return a new refresh_token — keep the old one
	if tokens.RefreshToken != "" {
		a.authState.RefreshToken = tokens.RefreshToken
	}

	return nil
}

// GetAccessToken returns the current access token
func (a *AuthService) GetAccessToken() string {
	return a.authState.AccessToken
}

// IsTokenExpired checks if the current token is expired or will expire soon
func (a *AuthService) IsTokenExpired() bool {
	if a.authState.AccessToken == "" {
		return true
	}

	// Check if token will expire within the threshold
	threshold := time.Now().Unix() + int64(a.config.TokenRefreshThreshold)
	return a.authState.ExpiryTime <= threshold
}

// EnsureValidToken ensures we have a valid access token
func (a *AuthService) EnsureValidToken() error {
	if a.authState.AccessToken == "" {
		return a.Authenticate()
	}

	if a.IsTokenExpired() {
		return a.RefreshToken()
	}

	return nil
}
