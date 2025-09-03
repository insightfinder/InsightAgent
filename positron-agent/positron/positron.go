package positron

import (
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	config "github.com/insightfinder/positron-agent/configs"
	"github.com/sirupsen/logrus"
)

// min helper function
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func NewService(config config.PositronConfig) *Service {
	// Create HTTP client with SSL verification settings
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: !config.VerifySSL,
		},
	}

	client := &http.Client{
		Transport: tr,
		Timeout:   180 * time.Second,
	}

	baseURL := fmt.Sprintf("https://%s:%d/api/v1",
		config.ControllerHost, config.ControllerPort)

	service := &Service{
		Config:     config,
		HttpClient: client,
		BaseURL:    baseURL,
	}

	return service
}

// HealthCheck performs a simple health check
func (s *Service) HealthCheck() error {
	// Try to get endpoints list as a health check
	_, err := s.GetEndpoints()
	return err
}

// GetEndpoints retrieves all endpoints from the Positron controller
func (s *Service) GetEndpoints() ([]Endpoint, error) {
	url := fmt.Sprintf("%s/endpoint/list/all", s.BaseURL)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %v", err)
	}

	// Add Basic Auth header
	auth := base64.StdEncoding.EncodeToString([]byte(s.Config.Username + ":" + s.Config.Password))
	req.Header.Add("Authorization", "Basic "+auth)

	resp, err := s.HttpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	var response EndpointResponse
	if err := json.Unmarshal(body, &response); err != nil {
		logrus.Errorf("Failed to decode JSON response. Response body: %s", string(body)[:min(len(body), 500)])
		return nil, fmt.Errorf("failed to decode response: %v", err)
	}

	logrus.Debugf("Retrieved %d endpoints", len(response.Data))
	return response.Data, nil
}

// GetDevices retrieves all devices from the Positron controller
func (s *Service) GetDevices() ([]Device, error) {
	url := fmt.Sprintf("%s/device/list", s.BaseURL)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %v", err)
	}

	// Add Basic Auth header
	auth := base64.StdEncoding.EncodeToString([]byte(s.Config.Username + ":" + s.Config.Password))
	req.Header.Add("Authorization", "Basic "+auth)
	req.Header.Add("Content-Type", "application/json")
	req.Header.Add("Accept", "application/json")

	// Add required parameters
	req.Header.Add("filter", "")
	req.Header.Add("mode", "auto")
	req.Header.Add("pageNo", "0")
	req.Header.Add("pageSize", "5000")
	req.Header.Add("param", "")
	req.Header.Add("sessionId", "123")
	req.Header.Add("sortBy", "")
	req.Header.Add("sortDir", "")

	resp, err := s.HttpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	var response DeviceResponse
	if err := json.Unmarshal(body, &response); err != nil {
		logrus.Errorf("Failed to decode JSON response. Response body: %s", string(body)[:min(len(body), 500)])
		return nil, fmt.Errorf("failed to decode response: %v", err)
	}

	logrus.Debugf("Retrieved %d devices", len(response.Data))
	return response.Data, nil
}

// GetAlarms retrieves all alarms from the Positron controller
func (s *Service) GetAlarms() ([]Alarm, error) {
	url := fmt.Sprintf("%s/alarm/list", s.BaseURL)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %v", err)
	}

	// Add Basic Auth header
	auth := base64.StdEncoding.EncodeToString([]byte(s.Config.Username + ":" + s.Config.Password))
	req.Header.Add("Authorization", "Basic "+auth)
	req.Header.Add("Content-Type", "application/json")
	req.Header.Add("Accept", "application/json")

	// Add required parameters
	req.Header.Add("filter", "")
	req.Header.Add("mode", "auto")
	req.Header.Add("pageNo", "0")
	req.Header.Add("pageSize", "5000")
	req.Header.Add("param", "")
	req.Header.Add("sessionId", "123")
	req.Header.Add("sortBy", "creationDate")
	req.Header.Add("sortDir", "desc")

	resp, err := s.HttpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	var response AlarmResponse
	if err := json.Unmarshal(body, &response); err != nil {
		logrus.Errorf("Failed to decode JSON response. Response body: %s", string(body)[:min(len(body), 500)])
		return nil, fmt.Errorf("failed to decode response: %v", err)
	}

	// Filter: only alarms received in the last minute and not yet sent
	now := time.Now().UTC()
	cutoff := now.Add(-1 * time.Minute)

	var filtered []Alarm
	var maxReceived time.Time

	parseTime := func(ts string) (time.Time, error) {
		// Try several common layouts; API example includes milliseconds and timezone offset
		layouts := []string{
			time.RFC3339Nano,                // 2025-09-02T06:29:37.631Z or with offset
			time.RFC3339,                    // 2025-09-02T06:29:37Z or with offset
			"2006-01-02T15:04:05.000-07:00", // explicit ms + offset
			"2006-01-02T15:04:05-07:00",     // no ms + offset
		}
		var lastErr error
		for _, l := range layouts {
			if t, err := time.Parse(l, ts); err == nil {
				return t.UTC(), nil
			} else {
				lastErr = err
			}
		}
		return time.Time{}, lastErr
	}

	s.SessionMutex.Lock()
	lastSent := s.LastSentAlarmReceived
	s.SessionMutex.Unlock()

	for _, a := range response.Data {
		// Use 'received' field as requested
		if a.Received == "" {
			continue
		}
		recvTime, err := parseTime(a.Received)
		if err != nil {
			logrus.Debugf("Skipping alarm due to received time parse error: %v, value=%s", err, a.Received)
			continue
		}

		// Only in last minute
		if recvTime.Before(cutoff) {
			continue
		}
		// Only newer than what we've already sent
		if !lastSent.IsZero() && !recvTime.After(lastSent) {
			continue
		}

		filtered = append(filtered, a)
		if recvTime.After(maxReceived) {
			maxReceived = recvTime
		}
	}

	// Update the watermark so we don't resend
	if !maxReceived.IsZero() {
		s.SessionMutex.Lock()
		if maxReceived.After(s.LastSentAlarmReceived) {
			s.LastSentAlarmReceived = maxReceived
		}
		s.SessionMutex.Unlock()
	}

	logrus.Debugf("Retrieved %d alarms, %d new in last minute (watermark=%s)", len(response.Data), len(filtered), s.LastSentAlarmReceived.Format(time.RFC3339Nano))
	return filtered, nil
}
