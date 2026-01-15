package netexperience

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/insightfinder/netexperience-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Wait waits for a token to become available (rate limiting)
func (rl *RateLimiter) Wait() {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	// Refill tokens based on time elapsed
	now := time.Now()
	elapsed := now.Sub(rl.lastRefill)
	tokensToAdd := int(elapsed / rl.refillRate)

	if tokensToAdd > 0 {
		rl.tokens += tokensToAdd
		if rl.tokens > rl.maxTokens {
			rl.tokens = rl.maxTokens
		}
		rl.lastRefill = rl.lastRefill.Add(time.Duration(tokensToAdd) * rl.refillRate)
	}

	// Wait if no tokens available
	for rl.tokens <= 0 {
		rl.mu.Unlock()
		time.Sleep(rl.refillRate)
		rl.mu.Lock()

		now = time.Now()
		elapsed = now.Sub(rl.lastRefill)
		tokensToAdd = int(elapsed / rl.refillRate)

		if tokensToAdd > 0 {
			rl.tokens += tokensToAdd
			if rl.tokens > rl.maxTokens {
				rl.tokens = rl.maxTokens
			}
			rl.lastRefill = rl.lastRefill.Add(time.Duration(tokensToAdd) * rl.refillRate)
		}
	}

	// Consume a token
	rl.tokens--
}

// makeAuthenticatedRequest makes an HTTP request with authentication and retry logic
func (s *Service) makeAuthenticatedRequest(method, urlStr string, body io.Reader) (*http.Response, error) {
	var lastErr error

	for attempt := 1; attempt <= s.config.TokenRetryAttempts; attempt++ {
		// Ensure we have a valid token
		if err := s.ensureValidToken(); err != nil {
			return nil, fmt.Errorf("failed to ensure valid token: %w", err)
		}

		// Wait for rate limiter
		s.rateLimiter.Wait()

		// Create request
		req, err := http.NewRequest(method, urlStr, body)
		if err != nil {
			return nil, fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Accept", "application/json")
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", s.GetAccessToken()))

		// Execute request
		resp, err := s.httpClient.Do(req)
		if err != nil {
			lastErr = err
			logrus.Warnf("Request attempt %d failed: %v", attempt, err)
			if attempt < s.config.TokenRetryAttempts {
				time.Sleep(time.Duration(s.config.TokenRetryDelay) * time.Second)
			}
			continue
		}

		// Check for authentication errors
		if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
			resp.Body.Close()
			logrus.Warnf("Authentication failed (status %d), attempting to refresh token", resp.StatusCode)

			// Try to refresh/re-login
			if err := s.refreshAccessToken(); err != nil {
				logrus.Warnf("Token refresh failed, attempting re-login: %v", err)
				if err := s.loginWithRetry(); err != nil {
					return nil, fmt.Errorf("failed to re-authenticate: %w", err)
				}
			}

			if attempt < s.config.TokenRetryAttempts {
				time.Sleep(time.Duration(s.config.TokenRetryDelay) * time.Second)
			}
			continue
		}

		return resp, nil
	}

	return nil, fmt.Errorf("request failed after %d attempts: %w", s.config.TokenRetryAttempts, lastErr)
}

// GetCustomers retrieves all customers for the service provider
func (s *Service) GetCustomers() ([]*models.Customer, error) {
	logrus.Debug("Fetching customers from API...")

	urlStr := fmt.Sprintf("%s/portal/cmap/customer/forSp?serviceProviderId=%d&name=&operationalState=",
		s.config.BaseURL, s.config.ServiceProviderID)

	resp, err := s.makeAuthenticatedRequest("GET", urlStr, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to get customers: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("get customers failed with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var customers []*models.Customer
	if err := json.NewDecoder(resp.Body).Decode(&customers); err != nil {
		return nil, fmt.Errorf("failed to decode customers response: %w", err)
	}

	logrus.Infof("Retrieved %d customers", len(customers))
	return customers, nil
}

// GetEquipmentForCustomer retrieves all equipment for a specific customer
func (s *Service) GetEquipmentForCustomer(customerID int) ([]*models.Equipment, error) {
	logrus.Debugf("Fetching equipment for customer %d...", customerID)

	var allEquipment []*models.Equipment
	var paginationContext *models.PaginationContext

	for {
		var urlStr string
		if paginationContext != nil {
			// Format pagination context with newlines and indentation like the API expects
			contextJSON := fmt.Sprintf(`{
        "model_type": "PaginationContext",
        "cursor": "%s",
        "lastPage": %t,
        "lastReturnedPageNumber": %d,
        "maxItemsPerPage": %d,
        "totalItemsReturned": %d
    }`, paginationContext.Cursor, paginationContext.LastPage, paginationContext.LastReturnedPageNumber,
				paginationContext.MaxItemsPerPage, paginationContext.TotalItemsReturned)

			urlStr = fmt.Sprintf("%s/portal/equipment/forCustomer?customerId=%d&paginationContext=%s",
				s.config.BaseURL, customerID, url.QueryEscape(contextJSON))
		} else {
			urlStr = fmt.Sprintf("%s/portal/equipment/forCustomer?customerId=%d",
				s.config.BaseURL, customerID)
		}

		resp, err := s.makeAuthenticatedRequest("GET", urlStr, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to get equipment: %w", err)
		}

		if resp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			return nil, fmt.Errorf("get equipment failed with status %d: %s", resp.StatusCode, string(bodyBytes))
		}

		var paginatedResp struct {
			Items   []*models.Equipment      `json:"items"`
			Context models.PaginationContext `json:"context"`
		}

		if err := json.NewDecoder(resp.Body).Decode(&paginatedResp); err != nil {
			resp.Body.Close()
			return nil, fmt.Errorf("failed to decode equipment response: %w", err)
		}
		resp.Body.Close()

		allEquipment = append(allEquipment, paginatedResp.Items...)

		// Check if we need to fetch more pages
		if paginatedResp.Context.LastPage || paginatedResp.Context.TotalItemsReturned < paginatedResp.Context.MaxItemsPerPage {
			break
		}

		paginationContext = &paginatedResp.Context
	}

	logrus.Debugf("Retrieved %d equipment items for customer %d", len(allEquipment), customerID)
	return allEquipment, nil
}

// GetServiceMetrics retrieves service metrics for equipment
func (s *Service) GetServiceMetrics(customerID int, equipmentIDs []int, fromTime, toTime int64) ([]*models.ServiceMetric, error) {
	if len(equipmentIDs) == 0 {
		return nil, nil
	}

	// Build equipment IDs parameter
	equipmentIDsParam := ""
	for i, id := range equipmentIDs {
		if i > 0 {
			equipmentIDsParam += ","
		}
		equipmentIDsParam += fmt.Sprintf("%d", id)
	}

	logrus.Debugf("Fetching service metrics for customer %d, equipment IDs: %s, time range: %d-%d",
		customerID, equipmentIDsParam, fromTime, toTime)

	var allMetrics []*models.ServiceMetric
	var paginationContext *models.PaginationContext

	for {
		var urlStr string
		baseURL := fmt.Sprintf("%s/portal/serviceMetric/forCustomer?fromTime=%d&toTime=%d&customerId=%d&equipmentIds=%s&dataTypes=ApNode,SwitchNode,Client",
			s.config.BaseURL, fromTime, toTime, customerID, url.QueryEscape(equipmentIDsParam))

		if paginationContext != nil {
			// Format pagination context with newlines and indentation like the API expects
			contextJSON := fmt.Sprintf(`{
        "model_type": "PaginationContext",
        "cursor": "%s",
        "lastPage": %t,
        "lastReturnedPageNumber": %d,
        "maxItemsPerPage": %d,
        "totalItemsReturned": %d
    }`, paginationContext.Cursor, paginationContext.LastPage, paginationContext.LastReturnedPageNumber,
				paginationContext.MaxItemsPerPage, paginationContext.TotalItemsReturned)

			urlStr = fmt.Sprintf("%s&paginationContext=%s", baseURL, url.QueryEscape(contextJSON))
		} else {
			urlStr = baseURL
		}

		resp, err := s.makeAuthenticatedRequest("GET", urlStr, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to get service metrics: %w", err)
		}

		if resp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			return nil, fmt.Errorf("get service metrics failed with status %d: %s", resp.StatusCode, string(bodyBytes))
		}

		var paginatedResp struct {
			Items   []json.RawMessage        `json:"items"`
			Context models.PaginationContext `json:"context"`
		}

		if err := json.NewDecoder(resp.Body).Decode(&paginatedResp); err != nil {
			resp.Body.Close()
			return nil, fmt.Errorf("failed to decode service metrics response: %w", err)
		}
		resp.Body.Close()

		// Parse each item
		for _, item := range paginatedResp.Items {
			var metric models.ServiceMetric
			if err := json.Unmarshal(item, &metric); err != nil {
				logrus.Warnf("Failed to parse service metric: %v", err)
				continue
			}

			// Parse the details based on dataType (use tagged switch with default)
			var temp struct {
				Details json.RawMessage `json:"details"`
			}
			_ = json.Unmarshal(item, &temp)

			switch metric.DataType {
			case "ApNode":
				var details models.ApNodeMetrics
				if err := json.Unmarshal(temp.Details, &details); err == nil {
					metric.Details = details
				} else {
					logrus.Debugf("Failed to parse ApNode details: %v", err)
				}
			case "Client":
				var details models.ClientMetrics
				if err := json.Unmarshal(temp.Details, &details); err == nil {
					metric.Details = details
				} else {
					logrus.Debugf("Failed to parse Client details: %v", err)
				}
			default:
				// Unknown/unsupported types (e.g., SwitchNode) are ignored for now per plan
				logrus.Debugf("Unhandled ServiceMetric dataType: %s", metric.DataType)
			}

			allMetrics = append(allMetrics, &metric)
		}

		// Check if we need to fetch more pages
		if paginatedResp.Context.LastPage || paginatedResp.Context.TotalItemsReturned < paginatedResp.Context.MaxItemsPerPage {
			break
		}

		paginationContext = &paginatedResp.Context
	}

	logrus.Debugf("Retrieved %d service metrics for customer %d", len(allMetrics), customerID)
	return allMetrics, nil
}

// GetEquipmentIPAddress fetches the IP address for a specific equipment
func (s *Service) GetEquipmentIPAddress(customerID, equipmentID int) (string, error) {
	urlStr := fmt.Sprintf("%s/portal/status/forEquipment?customerId=%d&equipmentId=%d",
		s.config.BaseURL, customerID, equipmentID)

	resp, err := s.makeAuthenticatedRequest("GET", urlStr, nil)
	if err != nil {
		return "", fmt.Errorf("failed to get equipment status: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("get equipment status failed with status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	// Parse the response array
	var statuses []struct {
		StatusDataType string `json:"statusDataType"`
		Details        struct {
			ReportedIpV4Addr string `json:"reportedIpV4Addr"`
		} `json:"details"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&statuses); err != nil {
		return "", fmt.Errorf("failed to decode equipment status response: %w", err)
	}

	// Find the PROTOCOL status which contains the IP address
	for _, status := range statuses {
		if status.StatusDataType == "PROTOCOL" && status.Details.ReportedIpV4Addr != "" {
			return status.Details.ReportedIpV4Addr, nil
		}
	}

	return "", nil // No IP address found
}
