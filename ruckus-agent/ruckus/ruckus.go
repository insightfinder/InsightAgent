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
	"github.com/insightfinder/ruckus-agent/pkg/models"
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

	return &Service{
		config:        config,
		httpClient:    client,
		baseURL:       baseURL,
		sessionExpiry: 30 * time.Minute, // Default session expiry
	}
}

func (s *Service) Authenticate() error {
	s.sessionMutex.Lock()
	defer s.sessionMutex.Unlock()

	loginURL := fmt.Sprintf("%s/session", s.baseURL)
	logrus.Debugf("Authenticating to: %s", loginURL)

	payload := map[string]string{
		"username": s.config.Username,
		"password": s.config.Password,
	}

	jsonPayload, _ := json.Marshal(payload)

	resp, err := s.httpClient.Post(loginURL, "application/json", bytes.NewBuffer(jsonPayload))
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

	s.lastAuthTime = time.Now()
	logrus.Debug("Successfully authenticated with Ruckus controller")
	return nil
}

// Check if session needs renewal and renew if necessary
func (s *Service) ensureValidSession() error {
	s.sessionMutex.RLock()
	needsRenewal := time.Since(s.lastAuthTime) > s.sessionExpiry-5*time.Minute // Renew 5 minutes before expiry
	s.sessionMutex.RUnlock()

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

	resp, err := s.httpClient.Do(req)
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
			return s.httpClient.Do(newReq)
		}

		// If it's not a session expiration, return the original error
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(bodyBytes[:n]))
	}

	return resp, nil
}

// Helper function for GET requests with session management
func (s *Service) get(url string) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	return s.executeRequest(req)
}

// Helper function for POST requests with session management
func (s *Service) post(url string, body []byte) (*http.Response, error) {
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	return s.executeRequest(req)
}

// Get total count of APs
func (s *Service) GetAPTotalCount() (int, error) {
	url := fmt.Sprintf("%s/aps/totalCount", s.baseURL)
	logrus.Debugf("Fetching total AP count from URL: %s", url)

	resp, err := s.get(url)
	if err != nil {
		return 0, fmt.Errorf("failed to get AP total count: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp ErrorResponse
		bodyBytes := make([]byte, 1024)
		n, _ := resp.Body.Read(bodyBytes)

		if json.Unmarshal(bodyBytes[:n], &errorResp) == nil {
			return 0, fmt.Errorf("AP total count request failed (code %d): %s", errorResp.Code, errorResp.Message)
		}
		return 0, fmt.Errorf("AP total count request failed with status: %d, body: %s", resp.StatusCode, string(bodyBytes[:n]))
	}

	// The API returns just the number directly, not a JSON object
	var totalCount int
	if err := json.NewDecoder(resp.Body).Decode(&totalCount); err != nil {
		return 0, fmt.Errorf("failed to decode AP total count response: %v", err)
	}

	logrus.Debugf("Total AP count: %d", totalCount)
	return totalCount, nil
}

// Get paginated AP list
func (s *Service) GetAPListPaginated(index, listSize int) (*models.APListResponse, error) {
	url := fmt.Sprintf("%s/aps?index=%d&listSize=%d", s.baseURL, index, listSize)
	logrus.Debugf("Fetching AP list from URL: %s", url)

	resp, err := s.get(url)
	if err != nil {
		return nil, fmt.Errorf("failed to get AP list: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp ErrorResponse
		if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
			return nil, fmt.Errorf("AP list request failed (code %d): %s", errorResp.Code, errorResp.Message)
		}
		return nil, fmt.Errorf("AP list request failed with status: %d", resp.StatusCode)
	}

	var apList models.APListResponse
	if err := json.NewDecoder(resp.Body).Decode(&apList); err != nil {
		return nil, fmt.Errorf("failed to decode AP list response: %v", err)
	}

	return &apList, nil
}

// Get all APs using pagination
func (s *Service) GetAllAPs() ([]models.APInfo, error) {
	// First get total count
	totalCount, err := s.GetAPTotalCount()
	if err != nil {
		return nil, fmt.Errorf("failed to get AP total count: %v", err)
	}

	logrus.Infof("Total APs in deployment: %d", totalCount)

	if totalCount == 0 {
		return []models.APInfo{}, nil
	}

	var allAPs []models.APInfo
	pageSize := 1000 // Maximum allowed by API

	// Calculate number of pages needed
	totalPages := (totalCount + pageSize - 1) / pageSize

	for page := 0; page < totalPages; page++ {
		index := page * pageSize

		logrus.Debugf("Fetching AP page %d/%d (index: %d, size: %d)",
			page+1, totalPages, index, pageSize)

		apList, err := s.GetAPListPaginated(index, pageSize)
		if err != nil {
			return nil, fmt.Errorf("failed to get AP list page %d: %v", page, err)
		}

		allAPs = append(allAPs, apList.List...)

		logrus.Debugf("Retrieved %d APs in page %d (total so far: %d)",
			len(apList.List), page+1, len(allAPs))

		// If we got fewer APs than requested, we've reached the end
		if len(apList.List) < pageSize {
			break
		}

		// Small delay between requests to avoid overwhelming the controller
		time.Sleep(50 * time.Millisecond)
	}

	logrus.Infof("Successfully retrieved %d APs across %d pages", len(allAPs), totalPages)
	return allAPs, nil
}

func (s *Service) GetAPList() (*models.APListResponse, error) {
	// For backward compatibility, get first 100 APs
	return s.GetAPListPaginated(0, 100)
}

func (s *Service) GetAPDetail(mac string) (*models.APDetailResponse, error) {
	url := fmt.Sprintf("%s/query/ap", s.baseURL)

	request := models.APQueryRequest{
		ExtraFilters: []models.Filter{
			{
				Type:  "AP",
				Value: mac,
			},
		},
	}

	jsonPayload, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal AP query request: %v", err)
	}

	resp, err := s.post(url, jsonPayload)
	if err != nil {
		return nil, fmt.Errorf("failed to get AP detail: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp ErrorResponse
		if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
			return nil, fmt.Errorf("AP detail request failed (code %d): %s", errorResp.Code, errorResp.Message)
		}
		return nil, fmt.Errorf("AP detail request failed with status: %d", resp.StatusCode)
	}

	var apDetail models.APDetailResponse
	if err := json.NewDecoder(resp.Body).Decode(&apDetail); err != nil {
		return nil, fmt.Errorf("failed to decode AP detail response: %v", err)
	}

	return &apDetail, nil
}

// Optimized method to get all AP details with better performance and session management
func (s *Service) GetAllAPDetails() ([]models.APDetail, error) {
	// Get all APs using efficient pagination
	allAPs, err := s.GetAllAPs()
	if err != nil {
		return nil, fmt.Errorf("failed to get all APs: %v", err)
	}

	if len(allAPs) == 0 {
		logrus.Warn("No APs found in deployment")
		return []models.APDetail{}, nil
	}

	logrus.Infof("Collecting detailed metrics for %d APs", len(allAPs))

	var allDetails []models.APDetail
	successCount := 0
	errorCount := 0

	// Process APs in batches to avoid overwhelming the controller
	batchSize := 10
	for i := 0; i < len(allAPs); i += batchSize {
		end := i + batchSize
		if end > len(allAPs) {
			end = len(allAPs)
		}

		batch := allAPs[i:end]
		logrus.Debugf("Processing batch %d-%d of %d APs", i+1, end, len(allAPs))

		// Renew session if needed before processing batch
		if err := s.ensureValidSession(); err != nil {
			logrus.Warnf("Failed to ensure valid session before batch: %v", err)
		}

		// Process each AP in the batch
		for j, ap := range batch {
			logrus.Debugf("Getting details for AP %d/%d: %s (%s)",
				i+j+1, len(allAPs), ap.Name, ap.MAC)

			detail, err := s.GetAPDetail(ap.MAC)
			if err != nil {
				logrus.Warnf("Failed to get details for AP %s (%s): %v",
					ap.Name, ap.MAC, err)
				errorCount++
				continue
			}

			if len(detail.List) > 0 {
				allDetails = append(allDetails, detail.List[0])
				successCount++
			} else {
				logrus.Warnf("No details returned for AP %s (%s)", ap.Name, ap.MAC)
				errorCount++
			}

			// Small delay between individual requests
			time.Sleep(100 * time.Millisecond)
		}

		// Longer delay between batches
		if end < len(allAPs) {
			time.Sleep(500 * time.Millisecond)
		}
	}

	logrus.Infof("AP detail collection complete: %d successful, %d failed, %d total",
		successCount, errorCount, len(allAPs))

	if successCount == 0 {
		return nil, fmt.Errorf("failed to collect details for any APs")
	}

	return allDetails, nil
}

// Get AP details for a specific batch of MAC addresses (for parallel processing)
func (s *Service) GetAPDetailsBatch(macs []string) ([]models.APDetail, error) {
	var details []models.APDetail

	for _, mac := range macs {
		detail, err := s.GetAPDetail(mac)
		if err != nil {
			logrus.Warnf("Failed to get details for AP %s: %v", mac, err)
			continue
		}

		if len(detail.List) > 0 {
			details = append(details, detail.List[0])
		}

		// Small delay between requests
		time.Sleep(100 * time.Millisecond)
	}

	return details, nil
}

// Health check method to verify connectivity
func (s *Service) HealthCheck() error {
	_, err := s.GetAPTotalCount()
	return err
}
