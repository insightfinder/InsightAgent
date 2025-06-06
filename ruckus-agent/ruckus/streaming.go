package ruckus

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Optimized streaming version using bulk query with pagination
func (s *Service) GetAllAPDetailsStreamingBulk(ctx context.Context,
	processor func([]models.APDetail) error, chunkSize int) error {

	logrus.Info("Starting streaming bulk AP details collection")

	page := 1
	limit := 1000
	totalProcessed := 0

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		logrus.Infof("Fetching and processing page %d with limit %d", page, limit)

		request := APBulkQueryRequest{
			Filters: []Filter{}, // Empty filters = get all APs
			Page:    page,
			Limit:   limit,
		}

		url := fmt.Sprintf("%s/query/ap", s.BaseURL)
		jsonPayload, err := json.Marshal(request)
		if err != nil {
			return fmt.Errorf("failed to marshal bulk query request: %v", err)
		}

		resp, err := s.post(url, jsonPayload)
		if err != nil {
			return fmt.Errorf("failed to execute bulk AP query: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			var errorResp ErrorResponse
			if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
				return fmt.Errorf("bulk AP query failed (code %d): %s", errorResp.Code, errorResp.Message)
			}
			return fmt.Errorf("bulk AP query failed with status: %d", resp.StatusCode)
		}

		var queryResponse models.APDetailResponse
		if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
			return fmt.Errorf("failed to decode bulk query response: %v", err)
		}

		if len(queryResponse.List) == 0 {
			break
		}

		// Process this page's data in chunks
		pageData := queryResponse.List
		for i := 0; i < len(pageData); i += chunkSize {
			end := i + chunkSize
			if end > len(pageData) {
				end = len(pageData)
			}

			chunk := pageData[i:end]

			if err := processor(chunk); err != nil {
				return fmt.Errorf("processor failed for chunk %d-%d: %v", i, end, err)
			}

			totalProcessed += len(chunk)
		}

		logrus.Infof("Page %d processed: %d APs (total: %d)",
			page, len(queryResponse.List), totalProcessed)

		// Check if we got fewer results than limit (last page) or no more data
		if len(queryResponse.List) < limit || !queryResponse.HasMore {
			break
		}

		page++
		time.Sleep(100 * time.Millisecond) // Small delay between requests
	}

	logrus.Infof("Streaming bulk collection complete: processed %d APs total", totalProcessed)
	return nil
}
