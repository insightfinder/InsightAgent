package insightfinder

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/sirupsen/logrus"
)

// Send log data using the same format as Python implementation

// Send log data - format matching Python implementation
func (s *Service) SendLogDataBasic(logEntries []LogData) error {
	if len(logEntries) == 0 {
		return nil
	}

	// Convert log entries to the format expected by customprojectrawdata API
	var logDataList []map[string]interface{}
	for _, entry := range logEntries {
		logData := map[string]interface{}{
			"timestamp":     entry.TimeStamp,
			"tag":           entry.Tag,
			"data":          entry.Data,
			"componentName": entry.ComponentName,
			"ipAddress":     entry.IP,
		}
		logDataList = append(logDataList, logData)
	}

	return s.SendLogDataAsMap(logDataList)
}

// SendLogDataAsMap sends raw log data as maps (preserves IP addresses and other fields)
func (s *Service) SendLogDataAsMap(logs []map[string]interface{}) error {
	if len(logs) == 0 {
		return nil
	}

	// Convert log entries to the format expected by customprojectrawdata API
	var logDataList []map[string]interface{}
	for _, logEntry := range logs {
		logData := map[string]interface{}{
			"timestamp":     logEntry["timestamp"],
			"tag":           logEntry["tag"],
			"data":          logEntry["data"],
			"componentName": logEntry["componentName"],
		}

		// Add IP address if available in the log entry
		if ipAddr, exists := logEntry["ipAddress"]; exists && ipAddr != "" {
			logData["ipAddress"] = ipAddr
		}

		if zone, exists := logEntry["zone"]; exists && zone != "" {
			logData["zoneName"] = zone
		}

		logDataList = append(logDataList, logData)
	}

	// Convert to JSON string for metricData field (same as Python)
	metricDataJSON, err := json.Marshal(logDataList)
	if err != nil {
		return fmt.Errorf("failed to marshal log data: %v", err)
	}

	// Debug log the payload being sent
	logrus.Debugf("Sending log payload to InsightFinder: %s", string(metricDataJSON))

	// Create form data (same format as Python implementation)
	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "edgecore-agent"
	}
	hostname = strings.Split(hostname, ".")[0] // Get hostname before first dot

	form := url.Values{}
	form.Add("userName", s.config.UserName)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", s.LogProjectName)
	form.Add("instanceName", hostname)
	form.Add("agentType", "LogStreaming")
	form.Add("metricData", string(metricDataJSON))

	logrus.Debugln("logProjectName:", s.LogProjectName, "instanceName:", hostname)

	apiURL := fmt.Sprintf("%s%s", s.config.ServerURL, LOG_DATA_API)

	// Send with retry logic (matching Python implementation)
	var lastErr error
	for attempt := 1; attempt <= HTTP_RETRY_TIMES; attempt++ {
		req, err := http.NewRequest("POST", apiURL, strings.NewReader(form.Encode()))
		if err != nil {
			return fmt.Errorf("failed to create request: %v", err)
		}

		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

		resp, err := s.httpClient.Do(req)
		if err != nil {
			lastErr = err
			logrus.Warnf("Log send attempt %d/%d failed: %v", attempt, HTTP_RETRY_TIMES, err)
			if attempt < HTTP_RETRY_TIMES {
				time.Sleep(time.Duration(HTTP_RETRY_INTERVAL) * time.Second)
				continue
			}
			return fmt.Errorf("failed to send log data after %d attempts: %v", HTTP_RETRY_TIMES, err)
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			logrus.Infof("Successfully sent %d log entries to InsightFinder", len(logs))
			return nil
		} else {
			// Read response body for debugging
			bodyBytes := make([]byte, 1024)
			n, _ := resp.Body.Read(bodyBytes)
			lastErr = fmt.Errorf("request failed with status: %d, response: %s", resp.StatusCode, string(bodyBytes[:n]))
			logrus.Warnf("Log send attempt %d/%d failed with status %d", attempt, HTTP_RETRY_TIMES, resp.StatusCode)
			if attempt < HTTP_RETRY_TIMES {
				time.Sleep(time.Duration(HTTP_RETRY_INTERVAL) * time.Second)
				continue
			}
		}
	}

	return fmt.Errorf("failed to send log data after %d attempts: %v", HTTP_RETRY_TIMES, lastErr)
}
