package ruckus

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// GetAllClientsWithRSSISNR fetches all clients and returns a map of APMac -> ClientInfo
// This function takes only the first client for each AP to avoid duplicates
func (s *Service) GetAllClientsWithRSSISNR(ctx context.Context) (map[string]models.ClientInfo, error) {
	logrus.Info("Starting client data collection for RSSI/SNR metrics")

	// Get total count and first client data in one call
	totalCount, firstPageClients, err := s.getTotalClientCountAndFirstPage(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get total client count: %v", err)
	}

	if totalCount == 0 {
		logrus.Info("No clients found")
		return make(map[string]models.ClientInfo), nil
	}

	limit := 1000
	totalPages := (totalCount + limit - 1) / limit
	logrus.Infof("Total clients: %d, Pages needed: %d", totalCount, totalPages)

	// Map to store first client per AP (APMac -> ClientInfo)
	clientMap := make(map[string]models.ClientInfo)
	var mapMutex sync.Mutex

	// Process first page data we already have
	mapMutex.Lock()
	for _, client := range firstPageClients {
		// Only add if we haven't seen this AP before (first client wins)
		if _, exists := clientMap[client.APMac]; !exists {
			clientMap[client.APMac] = client
		}
	}
	mapMutex.Unlock()

	logrus.Debugf("First page processed: %d clients", len(firstPageClients))

	// If we only have one page, we're done
	if totalPages <= 1 {
		logrus.Infof("Client data collection complete: %d unique APs with RSSI/SNR data", len(clientMap))
		return clientMap, nil
	}

	// Determine batch size for concurrent fetching
	maxConcurrent := s.Config.MaxConcurrentRequests
	if maxConcurrent == 0 {
		maxConcurrent = 10
	}
	remainingPages := totalPages - 1 // We already processed page 1
	if remainingPages < maxConcurrent {
		maxConcurrent = remainingPages
	}

	// Process remaining pages in batches (starting from page 2 since we did page 1)
	for startPage := 2; startPage <= totalPages; startPage += maxConcurrent {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		default:
		}

		endPage := startPage + maxConcurrent - 1
		if endPage > totalPages {
			endPage = totalPages
		}

		logrus.Infof("Processing client pages %d to %d concurrently", startPage, endPage)

		// Fetch batch of pages concurrently
		pageResults, err := s.fetchClientPagesBatch(ctx, startPage, endPage, limit)
		if err != nil {
			return nil, fmt.Errorf("failed to fetch client pages %d-%d: %v", startPage, endPage, err)
		}

		// Process each page's data and update the map
		for page := startPage; page <= endPage; page++ {
			if pageData, exists := pageResults[page]; exists {
				mapMutex.Lock()
				for _, client := range pageData {
					// Only add if we haven't seen this AP before (first client wins)
					if _, exists := clientMap[client.APMac]; !exists {
						clientMap[client.APMac] = client
					}
				}
				mapMutex.Unlock()

				logrus.Debugf("Page %d processed: %d clients", page, len(pageData))
			}
		}
	}

	logrus.Infof("Client data collection complete: %d unique APs with RSSI/SNR data", len(clientMap))
	return clientMap, nil
}

// Get total client count and first page of clients in one call
func (s *Service) getTotalClientCountAndFirstPage(ctx context.Context) (int, []models.ClientInfo, error) {
	limit := 1000 // Use reasonable page size
	request := ClientBulkQueryRequest{
		Filters: []Filter{},
		Page:    1, // Ruckus uses 1-based pagination
		Limit:   limit,
	}

	url := fmt.Sprintf("%s/query/client", s.BaseURL)
	jsonPayload, err := json.Marshal(request)
	if err != nil {
		return 0, nil, fmt.Errorf("failed to marshal client request: %v", err)
	}

	resp, err := s.post(url, jsonPayload)
	if err != nil {
		return 0, nil, fmt.Errorf("failed to execute client query: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 0, nil, fmt.Errorf("client query failed with status: %d", resp.StatusCode)
	}

	var queryResponse models.ClientResponse
	if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
		return 0, nil, fmt.Errorf("failed to decode client response: %v", err)
	}

	return queryResponse.TotalCount, queryResponse.List, nil
}

// Fetch multiple client pages concurrently
func (s *Service) fetchClientPagesBatch(ctx context.Context, startPage, endPage, limit int) (map[int][]models.ClientInfo, error) {
	type pageResult struct {
		page    int
		clients []models.ClientInfo
		err     error
	}

	resultChan := make(chan pageResult, endPage-startPage+1)
	var wg sync.WaitGroup

	// Launch goroutines for each page in the batch
	for page := startPage; page <= endPage; page++ {
		wg.Add(1)
		go func(p int) {
			defer wg.Done()

			select {
			case <-ctx.Done():
				resultChan <- pageResult{page: p, err: ctx.Err()}
				return
			default:
			}

			clients, err := s.fetchClientPage(ctx, p, limit)
			resultChan <- pageResult{
				page:    p,
				clients: clients,
				err:     err,
			}
		}(page)
	}

	// Close channel when all goroutines complete
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	pageResults := make(map[int][]models.ClientInfo)
	for result := range resultChan {
		if result.err != nil {
			return nil, fmt.Errorf("failed to fetch client page %d: %v", result.page, result.err)
		}
		pageResults[result.page] = result.clients
	}

	return pageResults, nil
}

// Helper method to fetch a specific client page
func (s *Service) fetchClientPage(ctx context.Context, page, limit int) ([]models.ClientInfo, error) {
	logrus.Debugf("Fetching client page %d with limit %d", page, limit)

	request := ClientBulkQueryRequest{
		Filters: []Filter{}, // Empty filters = get all clients
		Page:    page,
		Limit:   limit,
	}

	url := fmt.Sprintf("%s/query/client", s.BaseURL)
	jsonPayload, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal client query request: %v", err)
	}

	resp, err := s.post(url, jsonPayload)
	if err != nil {
		return nil, fmt.Errorf("failed to execute client query: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp ErrorResponse
		if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
			return nil, fmt.Errorf("client query failed (code %d): %s", errorResp.Code, errorResp.Message)
		}
		return nil, fmt.Errorf("client query failed with status: %d", resp.StatusCode)
	}

	var queryResponse models.ClientResponse
	if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
		return nil, fmt.Errorf("failed to decode client query response: %v", err)
	}

	return queryResponse.List, nil
}

// EnrichAPDataWithClientMetrics enriches AP data with RSSI and SNR from client data
func EnrichAPDataWithClientMetrics(apDetails []models.APDetail, clientMap map[string]models.ClientInfo) []models.APDetail {
	enriched := make([]models.APDetail, len(apDetails))

	for i, ap := range apDetails {
		enriched[i] = ap // Copy the AP detail

		// Look for client data for this AP
		if clientInfo, exists := clientMap[ap.APMAC]; exists {
			// Convert RSSI to positive value and add to AP data
			positiveRSSI := clientInfo.RSSI
			if positiveRSSI < 0 {
				positiveRSSI = -positiveRSSI // Make positive
			}
			enriched[i].RSSI = &positiveRSSI
			enriched[i].SNR = &clientInfo.SNR
		}
	}

	return enriched
}
