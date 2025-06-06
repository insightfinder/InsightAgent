package ruckus

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Get all AP details using bulk query with pagination
func (s *Service) GetAllAPDetailsBulk() ([]models.APDetail, error) {
	logrus.Info("Starting bulk AP details collection using pagination")

	var allDetails []models.APDetail
	page := 1
	limit := 1000

	for {
		logrus.Infof("Fetching page %d with limit %d", page, limit)

		request := APBulkQueryRequest{
			Filters: []Filter{}, // Empty filters = get all APs
			Page:    page,
			Limit:   limit,
		}

		url := fmt.Sprintf("%s/query/ap", s.BaseURL)
		jsonPayload, err := json.Marshal(request)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal bulk query request: %v", err)
		}

		logrus.Debugf("Bulk query payload: %s", string(jsonPayload))

		resp, err := s.post(url, jsonPayload)
		if err != nil {
			return nil, fmt.Errorf("failed to execute bulk AP query: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			var errorResp ErrorResponse
			if json.NewDecoder(resp.Body).Decode(&errorResp) == nil {
				return nil, fmt.Errorf("bulk AP query failed (code %d): %s", errorResp.Code, errorResp.Message)
			}
			return nil, fmt.Errorf("bulk AP query failed with status: %d", resp.StatusCode)
		}

		var queryResponse models.APDetailResponse
		if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
			return nil, fmt.Errorf("failed to decode bulk query response: %v", err)
		}

		allDetails = append(allDetails, queryResponse.List...)

		logrus.Infof("Page %d: retrieved %d APs (total so far: %d, totalCount: %d)",
			page, len(queryResponse.List), len(allDetails), queryResponse.TotalCount)

		// Check if we got fewer results than limit (last page) or no more data
		if len(queryResponse.List) < limit || !queryResponse.HasMore {
			break
		}

		page++
		time.Sleep(100 * time.Millisecond) // Small delay between requests
	}

	logrus.Infof("Bulk collection complete: retrieved %d AP details total", len(allDetails))
	return allDetails, nil
}

// Main method to get all AP details
func (s *Service) GetAllAPDetails() ([]models.APDetail, error) {
	logrus.Info("Using bulk query with pagination for AP details collection")
	return s.GetAllAPDetailsBulk()
}
