package ruckus

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Get AP details for specific MAC addresses (batched)
func (s *Service) GetAPDetailsByMACs(macAddresses []string, batchSize int) ([]models.APDetail, error) {
	logrus.Infof("Getting AP details for %d specific MACs using batch size %d", len(macAddresses), batchSize)

	var allDetails []models.APDetail

	// Process MACs in batches
	for i := 0; i < len(macAddresses); i += batchSize {
		end := i + batchSize
		if end > len(macAddresses) {
			end = len(macAddresses)
		}

		batch := macAddresses[i:end]
		logrus.Debugf("Processing MAC batch %d-%d (%d MACs)", i+1, end, len(batch))

		// Create filters for the batch of MAC addresses
		var filters []Filter
		for _, mac := range batch {
			filters = append(filters, Filter{
				Type:  "AP",
				Value: mac,
			})
		}

		request := APBulkQueryRequest{
			Filters: filters,
			Page:    1,
			Limit:   batchSize * 2, // Buffer for safety
		}

		url := fmt.Sprintf("%s/query/ap", s.BaseURL)
		jsonPayload, err := json.Marshal(request)
		if err != nil {
			logrus.Warnf("Failed to marshal batch query: %v", err)
			continue
		}

		resp, err := s.post(url, jsonPayload)
		if err != nil {
			logrus.Warnf("Failed to execute batch query: %v", err)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			logrus.Warnf("Batch query failed with status: %d", resp.StatusCode)
			continue
		}

		var queryResponse models.APDetailResponse
		if err := json.NewDecoder(resp.Body).Decode(&queryResponse); err != nil {
			logrus.Warnf("Failed to decode batch response: %v", err)
			continue
		}

		allDetails = append(allDetails, queryResponse.List...)
		logrus.Infof("Batch %d-%d: retrieved %d APs", i+1, end, len(queryResponse.List))

		time.Sleep(200 * time.Millisecond) // Rate limiting
	}

	logrus.Infof("MAC-specific collection complete: retrieved %d AP details", len(allDetails))
	return allDetails, nil
}
