package netexperience

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	config "github.com/insightfinder/netexperience-agent/configs"
	"github.com/insightfinder/netexperience-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// NewService creates a new NetExperience service
func NewService(cfg config.NetExperienceConfig) *Service {
	// Calculate refill rate based on rate limit settings
	refillRate := time.Duration(cfg.RateLimitPeriod) * time.Second / time.Duration(cfg.RateLimitRequests)

	service := &Service{
		config: cfg,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		rateLimiter: &RateLimiter{
			tokens:     cfg.RateLimitRequests,
			maxTokens:  cfg.RateLimitRequests,
			refillRate: refillRate,
			lastRefill: time.Now(),
		},
		cache: &models.CachedData{
			Customers:           make(map[int]*models.Customer),
			EquipmentByCustomer: make(map[int][]*models.Equipment),
		},
	}

	return service
}

// Initialize performs initial authentication and cache loading
func (s *Service) Initialize() error {
	logrus.Info("Initializing NetExperience service...")

	// Perform initial login
	if err := s.login(); err != nil {
		return fmt.Errorf("initial login failed: %w", err)
	}

	logrus.Info("NetExperience service initialized successfully")
	return nil
}

// login authenticates with the NetExperience API
func (s *Service) login() error {
	logrus.Debug("Attempting to login to NetExperience API...")

	loginReq := LoginRequest{
		UserID:   s.config.UserID,
		Password: s.config.Password,
	}

	body, err := json.Marshal(loginReq)
	if err != nil {
		return fmt.Errorf("failed to marshal login request: %w", err)
	}

	url := fmt.Sprintf("%s/management/cmap/oauth2/token", s.config.BaseURL)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("failed to create login request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("login request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("login failed with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var tokenResp TokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return fmt.Errorf("failed to decode login response: %w", err)
	}

	s.tokenMutex.Lock()
	s.accessToken = tokenResp.AccessToken
	s.refreshToken = tokenResp.RefreshToken
	s.tokenExpiry = time.Now().Add(time.Duration(tokenResp.ExpiresIn) * time.Second)
	s.tokenMutex.Unlock()

	logrus.Info("Successfully logged in to NetExperience API")
	logrus.Debugf("Token will expire at: %s", s.tokenExpiry.Format(time.RFC3339))

	return nil
}

// refreshAccessToken refreshes the access token
func (s *Service) refreshAccessToken() error {
	logrus.Debug("Attempting to refresh access token...")

	s.tokenMutex.RLock()
	refreshToken := s.refreshToken
	currentToken := s.accessToken
	s.tokenMutex.RUnlock()

	refreshReq := RefreshRequest{
		UserID:       s.config.UserID,
		Password:     s.config.Password,
		RefreshToken: refreshToken,
	}

	body, err := json.Marshal(refreshReq)
	if err != nil {
		return fmt.Errorf("failed to marshal refresh request: %w", err)
	}

	url := fmt.Sprintf("%s/management/cmap/oauth2/refresh", s.config.BaseURL)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("failed to create refresh request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", currentToken))

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("refresh request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("token refresh failed with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var tokenResp TokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return fmt.Errorf("failed to decode refresh response: %w", err)
	}

	s.tokenMutex.Lock()
	s.accessToken = tokenResp.AccessToken
	s.refreshToken = tokenResp.RefreshToken
	s.tokenExpiry = time.Now().Add(time.Duration(tokenResp.ExpiresIn) * time.Second)
	s.tokenMutex.Unlock()

	logrus.Info("Successfully refreshed access token")
	logrus.Debugf("Token will expire at: %s", s.tokenExpiry.Format(time.RFC3339))

	return nil
}

// ensureValidToken ensures we have a valid access token
func (s *Service) ensureValidToken() error {
	s.tokenMutex.RLock()
	expiry := s.tokenExpiry
	hasToken := s.accessToken != ""
	s.tokenMutex.RUnlock()

	// If no token, login
	if !hasToken {
		return s.loginWithRetry()
	}

	// If token expires soon (within 5 minutes), refresh it
	if time.Until(expiry) < 5*time.Minute {
		logrus.Debug("Token expiring soon, attempting refresh...")
		if err := s.refreshAccessToken(); err != nil {
			logrus.Warnf("Token refresh failed, attempting re-login: %v", err)
			return s.loginWithRetry()
		}
	}

	return nil
}

// loginWithRetry attempts login with retry logic
func (s *Service) loginWithRetry() error {
	var lastErr error

	for attempt := 1; attempt <= s.config.TokenRetryAttempts; attempt++ {
		if attempt > 1 {
			logrus.Infof("Login retry attempt %d/%d", attempt, s.config.TokenRetryAttempts)
			time.Sleep(time.Duration(s.config.TokenRetryDelay) * time.Second)
		}

		if err := s.login(); err != nil {
			lastErr = err
			logrus.Warnf("Login attempt %d failed: %v", attempt, err)
			continue
		}

		return nil
	}

	return fmt.Errorf("login failed after %d attempts: %w", s.config.TokenRetryAttempts, lastErr)
}

// GetAccessToken returns the current access token (thread-safe)
func (s *Service) GetAccessToken() string {
	s.tokenMutex.RLock()
	defer s.tokenMutex.RUnlock()
	return s.accessToken
}

// StartTokenRefreshRoutine starts a background routine to refresh tokens periodically
func (s *Service) StartTokenRefreshRoutine(stopChan <-chan struct{}) {
	ticker := time.NewTicker(time.Duration(s.config.TokenRefreshInterval) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			logrus.Debug("Periodic token refresh triggered")
			if err := s.refreshAccessToken(); err != nil {
				logrus.Errorf("Periodic token refresh failed: %v", err)
				// Try to re-login
				if err := s.loginWithRetry(); err != nil {
					logrus.Errorf("Failed to re-login after refresh failure: %v", err)
				}
			}
		case <-stopChan:
			logrus.Info("Token refresh routine stopped")
			return
		}
	}
}
