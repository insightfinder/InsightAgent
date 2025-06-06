package insightfinder

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/sirupsen/logrus"
)

// ---------- Send log data ---------
// Intended for future use, currently not being used in the current implementation.

// Send log data
func (s *Service) SendLogData(logEntries []LogData) error {
	if len(logEntries) == 0 {
		return nil
	}

	payload := LogDataReceivePayload{
		UserName:         s.config.UserName,
		LicenseKey:       s.config.LicenseKey,
		ProjectName:      s.ProjectName,
		SystemName:       s.SystemName,
		InsightAgentType: "LogStreaming",
		LogDataList:      logEntries,
	}

	url := fmt.Sprintf("%s%s", s.config.ServerURL, LOG_DATA_API)

	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal log payload: %v", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonPayload))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("agent-type", "Stream")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send log data: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("log data request failed with status: %d", resp.StatusCode)
	}

	logrus.Infof("Successfully sent %d log entries to InsightFinder", len(logEntries))
	return nil
}
