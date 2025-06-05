package insightfinder

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	config "github.com/insightfinder/ruckus-agent/configs"
	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

type Service struct {
	config     config.InsightFinderConfig
	httpClient *http.Client
}

func NewService(config config.InsightFinderConfig) *Service {
	client := &http.Client{
		Timeout: 30 * time.Second,
	}

	return &Service{
		config:     config,
		httpClient: client,
	}
}

func (s *Service) SendMetrics(metrics []models.MetricData) error {
	if len(metrics) == 0 {
		return nil
	}

	url := fmt.Sprintf("%s/api/v1/customprojectrawdata", s.config.ServerURL)

	payload := map[string]interface{}{
		"licenseKey":  s.config.LicenseKey,
		"projectName": s.config.ProjectName,
		"userName":    s.config.UserName,
		"data":        metrics,
	}

	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal metrics payload: %v", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonPayload))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send metrics: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("metrics request failed with status: %d", resp.StatusCode)
	}

	logrus.Infof("Successfully sent %d metrics to InsightFinder", len(metrics))
	return nil
}
