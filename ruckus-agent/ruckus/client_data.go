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

// GetAllClientsWithRSSISNR fetches all clients and returns a map of APMac -> []ClientInfo
// This function collects all clients for each AP to calculate percentage metrics
func (s *Service) GetAllClientsWithRSSISNR(ctx context.Context) (map[string][]models.ClientInfo, error) {
	logrus.Info("Starting client data collection for RSSI/SNR metrics")

	// Get total count and first client data in one call
	totalCount, firstPageClients, err := s.getTotalClientCountAndFirstPage(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get total client count: %v", err)
	}

	if totalCount == 0 {
		logrus.Info("No clients found")
		return make(map[string][]models.ClientInfo), nil
	}

	limit := 1000
	totalPages := (totalCount + limit - 1) / limit
	logrus.Infof("Total clients: %d, Pages needed: %d", totalCount, totalPages)

	// Map to store all clients per AP (APMac -> []ClientInfo)
	clientMap := make(map[string][]models.ClientInfo)
	var mapMutex sync.Mutex

	// Process first page data we already have
	mapMutex.Lock()
	for _, client := range firstPageClients {
		// Add all clients for each AP
		clientMap[client.APMac] = append(clientMap[client.APMac], client)
	}
	mapMutex.Unlock()

	logrus.Debugf("First page processed: %d clients", len(firstPageClients))

	// If we only have one page, we're done
	if totalPages <= 1 {
		totalClients := 0
		for _, clients := range clientMap {
			totalClients += len(clients)
		}
		logrus.Infof("Client data collection complete: %d unique APs with %d total clients for RSSI/SNR data", len(clientMap), totalClients)
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
					// Add all clients for each AP
					clientMap[client.APMac] = append(clientMap[client.APMac], client)
				}
				mapMutex.Unlock()

				logrus.Debugf("Page %d processed: %d clients", page, len(pageData))
			}
		}
	}

	totalClients := 0
	for _, clients := range clientMap {
		totalClients += len(clients)
	}
	logrus.Infof("Client data collection complete: %d unique APs with %d total clients for RSSI/SNR data", len(clientMap), totalClients)
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

// calculateRSSIPercentages calculates the percentage of clients below RSSI thresholds
// If client count is below threshold, returns 0 for all percentages
func calculateRSSIPercentages(clients []models.ClientInfo, minClientThreshold int) (below74, below78, below80 float64) {
	if len(clients) == 0 {
		return 0, 0, 0
	}

	// If client count is below threshold, return 0 for percentages
	if len(clients) < minClientThreshold {
		return 0, 0, 0
	}

	var count74, count78, count80 int
	total := len(clients)

	for _, client := range clients {
		if client.RSSI < -74 {
			count74++
		}
		if client.RSSI < -78 {
			count78++
		}
		if client.RSSI < -80 {
			count80++
		}

	}

	below74 = float64(count74) / float64(total) * 100
	below78 = float64(count78) / float64(total) * 100
	below80 = float64(count80) / float64(total) * 100

	return below74, below78, below80
}

// calculateSNRPercentages calculates the percentage of clients below SNR thresholds
// If client count is below threshold, returns 0 for all percentages
func calculateSNRPercentages(clients []models.ClientInfo, minClientThreshold int) (below15, below18, below20 float64) {
	if len(clients) == 0 {
		return 0, 0, 0
	}

	// If client count is below threshold, return 0 for percentages
	if len(clients) < minClientThreshold {
		return 0, 0, 0
	}

	var count15, count18, count20 int
	total := len(clients)

	for _, client := range clients {
		if client.SNR < 15 {
			count15++
		}
		if client.SNR < 18 {
			count18++
		}
		if client.SNR < 20 {
			count20++
		}
	}

	below15 = float64(count15) / float64(total) * 100
	below18 = float64(count18) / float64(total) * 100
	below20 = float64(count20) / float64(total) * 100

	return below15, below18, below20
}

// EnrichAPDataWithClientMetrics enriches AP data with RSSI and SNR from client data
func EnrichAPDataWithClientMetrics(apDetails []models.APDetail, clientMap map[string][]models.ClientInfo, rssiThreshold, snrThreshold int) []models.APDetail {
	enriched := make([]models.APDetail, len(apDetails))

	for i, ap := range apDetails {
		enriched[i] = ap // Copy the AP detail

		// Look for client data for this AP
		if clients, exists := clientMap[ap.APMAC]; exists && len(clients) > 0 {
			// Always calculate average RSSI and SNR from all clients
			var totalRSSI, totalSNR int
			for _, client := range clients {
				totalRSSI += client.RSSI
				totalSNR += client.SNR
			}

			avgRSSI := totalRSSI / len(clients)
			avgSNR := totalSNR / len(clients)

			// Convert RSSI to positive value for backwards compatibility
			positiveRSSI := avgRSSI
			if positiveRSSI < 0 {
				positiveRSSI = -positiveRSSI // Make positive
			}
			enriched[i].RSSI = &positiveRSSI
			enriched[i].SNR = &avgSNR

			// Calculate percentage metrics with threshold consideration
			rssiBelow74, rssiBelow78, rssiBelow80 := calculateRSSIPercentages(clients, rssiThreshold)
			snrBelow15, snrBelow18, snrBelow20 := calculateSNRPercentages(clients, snrThreshold)

			// Add percentage metrics to AP
			enriched[i].RSSIPercentBelow74 = &rssiBelow74
			enriched[i].RSSIPercentBelow78 = &rssiBelow78
			enriched[i].RSSIPercentBelow80 = &rssiBelow80
			enriched[i].SNRPercentBelow15 = &snrBelow15
			enriched[i].SNRPercentBelow18 = &snrBelow18
			enriched[i].SNRPercentBelow20 = &snrBelow20
		}
	}

	return enriched
}
