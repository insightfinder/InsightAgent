package ruckus

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Get all AP details using bulk query with concurrent pagination
func (s *Service) GetAllAPDetailsBulk() ([]models.APDetail, error) {
	logrus.Info("Starting bulk AP details collection using concurrent pagination")

	limit := 1000

	// Get total count from API instead of fetching first page
	totalCount, err := s.GetTotalAPCount()
	if err != nil {
		return nil, fmt.Errorf("failed to get total AP count: %v", err)
	}

	if totalCount == 0 {
		logrus.Info("No APs found")
		return []models.APDetail{}, nil
	}

	// Calculate total number of pages needed
	totalPages := (totalCount + limit - 1) / limit
	logrus.Infof("Total count: %d, Pages needed: %d", totalCount, totalPages)

	// Determine batch size for concurrent fetching (max 10 concurrent requests)
	maxConcurrent := s.Config.MaxConcurrentRequests
	if maxConcurrent == 0 {
		maxConcurrent = 10
	}
	if totalPages < maxConcurrent {
		maxConcurrent = totalPages
	}

	// Create channels and wait group for concurrent processing
	type pageResult struct {
		page    int
		details []models.APDetail
		err     error
	}

	resultChan := make(chan pageResult, maxConcurrent)
	var wg sync.WaitGroup

	// Launch goroutines for all pages with concurrency limit
	semaphore := make(chan struct{}, maxConcurrent)

	for page := 1; page <= totalPages; page++ {
		wg.Add(1)
		go func(p int) {
			defer wg.Done()

			// Acquire semaphore
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			details, _, err := s.fetchAPPage(p, limit)
			resultChan <- pageResult{
				page:    p,
				details: details,
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
	allResults := make(map[int][]models.APDetail)

	for result := range resultChan {
		if result.err != nil {
			return nil, fmt.Errorf("failed to fetch page %d: %v", result.page, result.err)
		}
		allResults[result.page] = result.details
		logrus.Infof("Page %d: retrieved %d APs", result.page, len(result.details))
	}

	// Combine all results in correct order
	var allDetails []models.APDetail
	for page := 1; page <= totalPages; page++ {
		if details, exists := allResults[page]; exists {
			allDetails = append(allDetails, details...)
		}
	}

	logrus.Infof("Concurrent collection complete: retrieved %d AP details total", len(allDetails))
	return allDetails, nil
}

// Helper method to fetch a specific page
func (s *Service) fetchAPPage(page, limit int) ([]models.APDetail, int, error) {
	logrus.Debugf("Fetching page %d with limit %d", page, limit)

	request := APBulkQueryRequest{
		Filters: []Filter{}, // Empty filters = get all APs
		Page:    page,
		Limit:   limit,
	}

	url := fmt.Sprintf("%s/query/ap", s.BaseURL)
	jsonPayload, err := json.Marshal(request)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to marshal bulk query request: %v", err)
	}

	resp, err := s.post(url, jsonPayload)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to execute bulk AP query: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp ErrorResponse
		if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
			return nil, 0, fmt.Errorf("bulk AP query failed (code %d): %s", errorResp.Code, errorResp.Message)
		}
		return nil, 0, fmt.Errorf("bulk AP query failed with status: %d", resp.StatusCode)
	}

	var queryResponse models.APDetailResponse
	if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
		return nil, 0, fmt.Errorf("failed to decode bulk query response: %v", err)
	}

	return queryResponse.List, queryResponse.TotalCount, nil
}

// Main method to get all AP details
func (s *Service) GetAllAPDetails() ([]models.APDetail, error) {
	logrus.Info("Using concurrent bulk query with pagination for AP details collection")
	return s.GetAllAPDetailsBulk()
}
