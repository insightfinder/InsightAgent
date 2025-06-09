package ruckus

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Optimized streaming version using bulk query with concurrent pagination
func (s *Service) GetAllAPDetailsStreamingBulk(ctx context.Context,
	processor func([]models.APDetail) error, chunkSize int) error {

	logrus.Info("Starting streaming bulk AP details collection with concurrent fetching")

	limit := 1000

	// Get total count from API instead of fetching first page
	totalCount, err := s.GetTotalAPCount()
	if err != nil {
		return fmt.Errorf("failed to get total AP count: %v", err)
	}

	if totalCount == 0 {
		logrus.Info("No APs found")
		return nil
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

	// Process all pages in batches
	totalProcessed := 0
	for startPage := 1; startPage <= totalPages; startPage += maxConcurrent {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		endPage := startPage + maxConcurrent - 1
		if endPage > totalPages {
			endPage = totalPages
		}

		logrus.Infof("Processing pages %d to %d concurrently", startPage, endPage)

		// Fetch batch of pages concurrently
		pageResults, err := s.fetchPagesBatch(ctx, startPage, endPage, limit)
		if err != nil {
			return fmt.Errorf("failed to fetch pages %d-%d: %v", startPage, endPage, err)
		}

		// Process each page's data in order
		for page := startPage; page <= endPage; page++ {
			if pageData, exists := pageResults[page]; exists {
				if err := s.processPageData(pageData, processor, chunkSize); err != nil {
					return fmt.Errorf("failed to process page %d: %v", page, err)
				}
				totalProcessed += len(pageData)
				logrus.Infof("Page %d processed: %d APs (total: %d)",
					page, len(pageData), totalProcessed)
			}
		}

		// Small delay between batches to avoid overwhelming the server
		time.Sleep(100 * time.Millisecond)
	}

	logrus.Infof("Streaming bulk collection complete: processed %d APs total", totalProcessed)
	return nil
}

// Fetch multiple pages concurrently
func (s *Service) fetchPagesBatch(ctx context.Context, startPage, endPage, limit int) (map[int][]models.APDetail, error) {
	type pageResult struct {
		page    int
		details []models.APDetail
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

			details, _, err := s.fetchAPPageStreaming(ctx, p, limit)
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
	pageResults := make(map[int][]models.APDetail)
	for result := range resultChan {
		if result.err != nil {
			return nil, fmt.Errorf("failed to fetch page %d: %v", result.page, result.err)
		}
		pageResults[result.page] = result.details
	}

	return pageResults, nil
}

// Helper method to fetch a specific page for streaming
func (s *Service) fetchAPPageStreaming(ctx context.Context, page, limit int) ([]models.APDetail, int, error) {
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

// Helper method to process page data in chunks
func (s *Service) processPageData(pageData []models.APDetail, processor func([]models.APDetail) error, chunkSize int) error {
	for i := 0; i < len(pageData); i += chunkSize {
		end := i + chunkSize
		if end > len(pageData) {
			end = len(pageData)
		}

		chunk := pageData[i:end]
		if err := processor(chunk); err != nil {
			return fmt.Errorf("processor failed for chunk %d-%d: %v", i, end, err)
		}
	}
	return nil
}
