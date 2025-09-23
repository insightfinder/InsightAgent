package tarana

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"

	config "github.com/insightfinder/tarana-agent/configs"
	"github.com/sirupsen/logrus"
)

type Service struct {
	config               config.TaranaConfig
	client               *http.Client
	authState            *config.AuthState
	authMutex            sync.RWMutex
	SessionMutex         sync.RWMutex
	LastSentAlarmCreated time.Time
}

// NewService creates a new Tarana service
func NewService(cfg config.TaranaConfig) *Service {
	// Configure HTTP client
	transport := &http.Transport{}
	if !cfg.VerifySSL {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}

	client := &http.Client{
		Transport: transport,
		Timeout:   30 * time.Second,
	}

	return &Service{
		config:    cfg,
		client:    client,
		authState: &config.AuthState{},
	}
}

// Login authenticates with Tarana API
func (s *Service) Login() error {
	s.authMutex.Lock()
	defer s.authMutex.Unlock()

	loginURL := fmt.Sprintf("%s/api/tcs/v1/user-auth/login", s.config.BaseURL)

	// Create request with basic auth
	req, err := http.NewRequest("POST", loginURL, nil)
	if err != nil {
		return fmt.Errorf("failed to create login request: %v", err)
	}

	req.SetBasicAuth(s.config.Username, s.config.Password)
	req.Header.Set("Content-Type", "application/json")

	// Execute request
	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("login request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("login failed with status: %d", resp.StatusCode)
	}

	// Parse response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read login response: %v", err)
	}

	var loginResp LoginResponse
	if err := json.Unmarshal(body, &loginResp); err != nil {
		return fmt.Errorf("failed to parse login response: %v", err)
	}

	if loginResp.Error != "" {
		return fmt.Errorf("login API error: %s", loginResp.Error)
	}

	// Update auth state
	now := time.Now().Unix()
	s.authState.AccessToken = loginResp.Data.AccessToken
	s.authState.IDToken = loginResp.Data.IDToken
	s.authState.RefreshToken = loginResp.Data.RefreshToken
	s.authState.UserID = loginResp.Data.UserID
	s.authState.ExpiryTime = now + int64(loginResp.Data.ExpiryTimeSeconds)
	s.authState.LastRefreshed = now

	logrus.Info("Successfully authenticated with Tarana API")
	return nil
}

// RefreshToken refreshes the authentication token
func (s *Service) RefreshToken() error {
	s.authMutex.Lock()
	defer s.authMutex.Unlock()

	refreshURL := fmt.Sprintf("%s/api/tcs/v1/user-auth/refresh", s.config.BaseURL)

	req, err := http.NewRequest("POST", refreshURL, nil)
	if err != nil {
		return fmt.Errorf("failed to create refresh request: %v", err)
	}

	// Set cookies for refresh
	cookieValue := fmt.Sprintf("idToken=%s; refreshToken=%s; accessToken=%s; userId=%s",
		s.authState.IDToken, s.authState.RefreshToken, s.authState.AccessToken, s.authState.UserID)
	req.Header.Set("Cookie", cookieValue)
	req.Header.Set("Content-Type", "application/json")

	logrus.Debug("Attempting to refresh Tarana API token")

	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("refresh token request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		logrus.Warn("Token refresh failed, attempting re-login")
		return s.Login()
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read refresh response: %v", err)
	}

	var refreshResp RefreshTokenResponse
	if err := json.Unmarshal(body, &refreshResp); err != nil {
		return fmt.Errorf("failed to parse refresh response: %v", err)
	}

	if refreshResp.Error != "" {
		logrus.Warnf("Token refresh API error: %s, attempting re-login", refreshResp.Error)
		return s.Login()
	}

	// Validate that we received essential tokens
	if refreshResp.Data.AccessToken == "" || refreshResp.Data.IDToken == "" {
		logrus.Warn("Refresh response missing essential tokens, attempting re-login")
		return s.Login()
	}

	// Update auth state
	now := time.Now().Unix()
	s.authState.AccessToken = refreshResp.Data.AccessToken
	s.authState.IDToken = refreshResp.Data.IDToken

	// Only update refresh token if a new one is provided
	if refreshResp.Data.RefreshToken != nil {
		s.authState.RefreshToken = *refreshResp.Data.RefreshToken
	}

	// Update user ID if provided
	if refreshResp.Data.UserID != nil {
		s.authState.UserID = *refreshResp.Data.UserID
	}

	s.authState.ExpiryTime = now + int64(refreshResp.Data.ExpiryTimeSeconds)
	s.authState.LastRefreshed = now

	logrus.Debugf("Successfully refreshed Tarana API token (expires in %d seconds)", refreshResp.Data.ExpiryTimeSeconds)
	if refreshResp.Data.RefreshToken == nil {
		logrus.Debug("No new refresh token provided, keeping existing one")
	}
	return nil
}

// ensureAuthenticated checks token validity and refreshes if needed
func (s *Service) ensureAuthenticated() error {
	s.authMutex.RLock()
	tokenEmpty := s.authState.AccessToken == ""
	currentTime := time.Now().Unix()
	refreshThreshold := s.authState.ExpiryTime - int64(s.config.TokenRefreshThreshold)
	tokenExpired := currentTime >= refreshThreshold
	timeUntilExpiry := s.authState.ExpiryTime - currentTime
	s.authMutex.RUnlock()

	if tokenEmpty {
		logrus.Debug("Token is empty, performing login")
		return s.Login()
	}

	if tokenExpired {
		logrus.Debugf("Token needs refresh (expires in %d seconds, threshold: %d)",
			timeUntilExpiry, s.config.TokenRefreshThreshold)
		return s.RefreshToken()
	}

	logrus.Debugf("Token is valid (expires in %d seconds)", timeUntilExpiry)
	return nil
}

// makeAuthenticatedRequest makes a request with authentication headers
func (s *Service) makeAuthenticatedRequest(method, url string, payload interface{}) (*http.Response, error) {
	if err := s.ensureAuthenticated(); err != nil {
		return nil, fmt.Errorf("authentication failed: %v", err)
	}

	var reqBody []byte
	var err error
	if payload != nil {
		reqBody, err = json.Marshal(payload)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request payload: %v", err)
		}
	}

	req, err := http.NewRequest(method, url, bytes.NewBuffer(reqBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %v", err)
	}

	s.authMutex.RLock()
	cookieValue := fmt.Sprintf("idToken=%s; accessToken=%s", s.authState.IDToken, s.authState.AccessToken)
	s.authMutex.RUnlock()

	req.Header.Set("Cookie", cookieValue)
	req.Header.Set("Content-Type", "application/json")

	return s.client.Do(req)
}

// GetDevices fetches all devices from Tarana API
func (s *Service) GetDevices() ([]Device, error) {
	url := fmt.Sprintf("%s/api/nqs/v1/regions/devices/search?offset=0&count=5000", s.config.BaseURL)

	searchReq := DeviceSearchRequest{
		IDs:          s.config.RegionIDs,
		DeviceFilter: DeviceFilterRequest{},
	}

	resp, err := s.makeAuthenticatedRequest("POST", url, searchReq)
	if err != nil {
		return nil, fmt.Errorf("device search request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("device search failed with status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read device search response: %v", err)
	}

	var deviceResp DeviceSearchResponse
	if err := json.Unmarshal(body, &deviceResp); err != nil {
		return nil, fmt.Errorf("failed to parse device search response: %v", err)
	}

	if deviceResp.Error != "" {
		return nil, fmt.Errorf("device search API error: %s", deviceResp.Error)
	}

	logrus.Infof("Found %d devices", len(deviceResp.Data.Items))
	return deviceResp.Data.Items, nil
}

// GetMetrics fetches metrics for specified devices
func (s *Service) GetMetrics(serialNumbers []string) (*MetricsResponse, error) {
	url := fmt.Sprintf("%s/api/tmq/v5/radios/kpi/latest-per-radio", s.config.BaseURL)

	// Get KPIs from configuration
	var kpis []string
	for kpiPath := range s.config.KPIs {
		kpis = append(kpis, kpiPath)
	}

	logrus.Debugf("Collecting metrics for %d KPIs: %v", len(kpis), kpis)

	metricsReq := MetricsRequest{
		Filter: MetricsFilter{
			ResidentialNodes: serialNumbers,
		},
		KPIs:       kpis,
		PageNumber: 1,
		PageSize:   2000,
	}

	resp, err := s.makeAuthenticatedRequest("POST", url, metricsReq)
	if err != nil {
		return nil, fmt.Errorf("metrics request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("metrics request failed with status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read metrics response: %v", err)
	}

	var metricsResp MetricsResponse
	if err := json.Unmarshal(body, &metricsResp); err != nil {
		return nil, fmt.Errorf("failed to parse metrics response: %v", err)
	}

	if metricsResp.Error != "" {
		return nil, fmt.Errorf("metrics API error: %s", metricsResp.Error)
	}

	return &metricsResp, nil
}

// GetAlarms fetches alarms/logs from Tarana API
func (s *Service) GetAlarms() (*AlarmResponse, error) {
	url := fmt.Sprintf("%s/api/ttm/v1/radios/alarm/details", s.config.BaseURL)

	alarmReq := AlarmRequest{
		AlarmsFilters: []AlarmFilter{
			{
				Term:      "status",
				Type:      "EXACT",
				TermValue: []string{"NACK"},
			},
		},
		Filter: RegionFilter{
			Regions: s.config.RegionIDs,
		},
		From: 0,
		Size: 2048,
		Sort: []SortConfig{
			{
				Field: "time-created",
				Order: "DESC",
			},
		},
	}

	resp, err := s.makeAuthenticatedRequest("POST", url, alarmReq)
	if err != nil {
		return nil, fmt.Errorf("alarms request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("alarms request failed with status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read alarms response: %v", err)
	}

	var alarmResp AlarmResponse
	if err := json.Unmarshal(body, &alarmResp); err != nil {
		return nil, fmt.Errorf("failed to parse alarms response: %v", err)
	}

	if alarmResp.Error != "" {
		return nil, fmt.Errorf("alarms API error: %s", alarmResp.Error)
	}

	// Filter: only alarms created in the last minute and not yet sent
	now := time.Now().UTC()
	cutoff := now.Add(-1 * time.Minute)

	var filtered []AlarmDetail
	var maxCreated time.Time

	parseTime := func(ts int64) time.Time {
		// Convert nanosecond timestamp to time
		if ts > 1e12 { // If timestamp is in nanoseconds
			return time.Unix(0, ts).UTC()
		} else { // If timestamp is in milliseconds
			return time.Unix(0, ts*1e6).UTC()
		}
	}

	s.SessionMutex.Lock()
	lastSent := s.LastSentAlarmCreated
	s.SessionMutex.Unlock()

	for _, alarm := range alarmResp.Data.Details {
		createdTime := parseTime(alarm.TimeCreated)

		// Only in last minute
		if createdTime.Before(cutoff) {
			continue
		}
		// Only newer than what we've already sent
		if !lastSent.IsZero() && !createdTime.After(lastSent) {
			continue
		}

		filtered = append(filtered, alarm)
		if createdTime.After(maxCreated) {
			maxCreated = createdTime
		}
	}

	// Update the watermark so we don't resend
	if !maxCreated.IsZero() {
		s.SessionMutex.Lock()
		if maxCreated.After(s.LastSentAlarmCreated) {
			s.LastSentAlarmCreated = maxCreated
		}
		s.SessionMutex.Unlock()
	}

	logrus.Debugf("Retrieved %d alarms, %d new in last minute (watermark=%s)",
		len(alarmResp.Data.Details), len(filtered), s.LastSentAlarmCreated.Format(time.RFC3339Nano))

	// Create filtered response
	filteredResp := &AlarmResponse{
		Data: AlarmData{
			Details:     filtered,
			Count:       len(filtered),
			Offset:      alarmResp.Data.Offset,
			Total:       len(filtered),
			Description: alarmResp.Data.Description,
		},
		Error: alarmResp.Error,
	}

	return filteredResp, nil
}

// HealthCheck performs a basic health check by attempting to get devices
func (s *Service) HealthCheck() error {
	_, err := s.GetDevices()
	return err
}

// GetAuthStatus returns current authentication status for debugging
func (s *Service) GetAuthStatus() map[string]interface{} {
	s.authMutex.RLock()
	defer s.authMutex.RUnlock()

	now := time.Now().Unix()
	timeUntilExpiry := s.authState.ExpiryTime - now

	return map[string]interface{}{
		"authenticated":     s.authState.AccessToken != "",
		"user_id":           s.authState.UserID,
		"expiry_time":       s.authState.ExpiryTime,
		"time_until_expiry": timeUntilExpiry,
		"last_refreshed":    s.authState.LastRefreshed,
		"needs_refresh":     timeUntilExpiry <= int64(s.config.TokenRefreshThreshold),
	}
}
