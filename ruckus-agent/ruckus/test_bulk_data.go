package ruckus

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Test function to verify bulk query works
func (s *Service) TestBulkQuery() error {
	logrus.Info("Testing bulk query endpoint with pagination")

	request := APBulkQueryRequest{
		Filters: []Filter{}, // Empty filters
		Page:    1,
		Limit:   1000,
	}

	url := fmt.Sprintf("%s/query/ap", s.BaseURL)
	jsonPayload, _ := json.Marshal(request)

	logrus.Infof("Test payload: %s", string(jsonPayload))

	resp, err := s.post(url, jsonPayload)
	if err != nil {
		return fmt.Errorf("bulk query test failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes := make([]byte, 1024)
		n, _ := resp.Body.Read(bodyBytes)
		return fmt.Errorf("test failed with status %d, body: %s", resp.StatusCode, string(bodyBytes[:n]))
	}

	var queryResponse models.APDetailResponse
	if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
		return fmt.Errorf("failed to decode test response: %v", err)
	}

	logrus.Infof("Bulk query test successful!")
	logrus.Infof("- Total count: %d", queryResponse.TotalCount)
	logrus.Infof("- Retrieved: %d APs", len(queryResponse.List))
	logrus.Infof("- Has more: %t", queryResponse.HasMore)

	if len(queryResponse.List) > 0 {
		logrus.Infof("- First AP: %s (MAC: %s, Status: %s)",
			queryResponse.List[0].DeviceName, queryResponse.List[0].APMAC, queryResponse.List[0].Status)
	}

	return nil
}
