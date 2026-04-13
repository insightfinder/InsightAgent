package insightfinder

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"time"

	"github.com/insightfinder/splunk-agent/configs"
	"github.com/sirupsen/logrus"
)

const (
	logDataAPI      = "/api/v1/customprojectrawdata"
	projectEndpoint = "/api/v1/check-and-add-custom-project"
)

// NewService creates a configured InsightFinder service and runs Validate.
func NewService(cfg configs.InsightFinderConfig) *Service {
	svc := &Service{
		config:           cfg,
		httpClient:       &http.Client{Timeout: 180 * time.Second},
		ProjectName:      cfg.LogsProjectName,
		LogProjectName:   cfg.LogsProjectName,
		SystemName:       cfg.LogsSystemName,
		ProjectType:      "LOG",
		Container:        cfg.IsContainer,
		CloudType:        cfg.CloudType,
		InstanceType:     cfg.InstanceType,
		SamplingInterval: uint(cfg.SamplingInterval),
	}
	svc.updateDerivedTypes()
	return svc
}

func (s *Service) updateDerivedTypes() {
	s.DataType = "Log"
	if s.Container {
		s.InsightAgentType = "ContainerCustom"
	} else {
		s.InsightAgentType = "Custom"
	}
}

// Initialize ensures the project exists in InsightFinder (creates it if not).
func (s *Service) Initialize() error {
	logrus.Info("Initializing InsightFinder service...")
	if !s.createProjectIfNotExist() {
		return fmt.Errorf("failed to create or verify project: %s", s.config.LogsProjectName)
	}
	logrus.Info("InsightFinder service initialized successfully")
	return nil
}

// ConvertToLogData maps a slice of Splunk events to the LogData format expected
// by the InsightFinder API. Tag and componentName are resolved using the
// priority chain:
//  1. Query-level static value (tag_value / component_value)
//  2. Query-level field name  (tag_field / component_field)  → look up in event
//  3. Global static value
//  4. Global field name                                       → look up in event
//  5. Built-in defaults: "host" → tag, "sourcetype" → componentName
//
// The full Splunk event (all fields including _raw) is sent as structured JSON.
func (s *Service) ConvertToLogData(events []SplunkEventSlim, qCfg configs.QueryConfig) []LogData {
	out := make([]LogData, 0, len(events))
	for _, e := range events {
		tag := resolveField(
			e.Fields,
			qCfg.TagValue, qCfg.TagField,
			s.config.TagValue, s.config.TagField,
			"host",
		)
		component := resolveField(
			e.Fields,
			qCfg.ComponentValue, qCfg.ComponentField,
			s.config.ComponentValue, s.config.ComponentField,
			"sourcetype",
		)
		out = append(out, LogData{
			TimeStamp:     e.TimestampMs,
			Tag:           CleanDeviceName(tag),
			ComponentName: CleanDeviceName(component),
			Data:          e.Fields, // full structured JSON event
		})
	}
	return out
}

// SendLogData converts events and sends them to InsightFinder.
// qCfg carries the per-query field mapping overrides used during conversion.
func (s *Service) SendLogData(events []SplunkEventSlim, qCfg configs.QueryConfig) error {
	if len(events) == 0 {
		return nil
	}
	logData := s.ConvertToLogData(events, qCfg)
	return s.sendLogDataInternal(logData)
}

// sendLogDataInternal posts logDataList to /api/v1/customprojectrawdata.
func (s *Service) sendLogDataInternal(logEntries []LogData) error {
	if len(logEntries) == 0 {
		return nil
	}

	// Build the metricData JSON string (same format as Python agent).
	payload := make([]map[string]interface{}, 0, len(logEntries))
	for _, e := range logEntries {
		payload = append(payload, map[string]interface{}{
			"timestamp":     e.TimeStamp,
			"tag":           e.Tag,
			"data":          e.Data,
			"componentName": e.ComponentName,
		})
	}

	metricDataJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal log data: %w", err)
	}
	logrus.Debugf("Sending %d log entries to InsightFinder", len(logEntries))

	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "splunk-agent"
	}

	form := url.Values{}
	form.Add("userName", s.config.UserName)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", s.LogProjectName)
	form.Add("instanceName", hostname)
	form.Add("agentType", "LogStreaming")
	form.Add("metricData", string(metricDataJSON))

	apiURL := s.config.ServerURL + logDataAPI

	var lastErr error
	for attempt := 1; attempt <= s.config.RetryTimes; attempt++ {
		req, err := http.NewRequest("POST", apiURL, bytes.NewBufferString(form.Encode()))
		if err != nil {
			return fmt.Errorf("create request: %w", err)
		}
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

		resp, err := s.httpClient.Do(req)
		if err != nil {
			lastErr = err
			logrus.Warnf("IF send attempt %d/%d failed: %v", attempt, s.config.RetryTimes, err)
			if attempt < s.config.RetryTimes {
				time.Sleep(time.Duration(s.config.RetryInterval) * time.Second)
			}
			continue
		}

		body := make([]byte, 1024)
		n, _ := resp.Body.Read(body)
		resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			logrus.Infof("Sent %d log entries to InsightFinder", len(logEntries))
			return nil
		}
		lastErr = fmt.Errorf("status %d: %s", resp.StatusCode, string(body[:n]))
		logrus.Warnf("IF send attempt %d/%d: %v", attempt, s.config.RetryTimes, lastErr)
		if attempt < s.config.RetryTimes {
			time.Sleep(time.Duration(s.config.RetryInterval) * time.Second)
		}
	}
	return fmt.Errorf("failed after %d attempts: %w", s.config.RetryTimes, lastErr)
}

// ─── field resolution ─────────────────────────────────────────────────────────

// resolveField returns the tag or component value by walking the priority chain:
// query static value → query field lookup → global static value → global field
// lookup → hardcoded default field name.
func resolveField(
	fields map[string]interface{},
	queryValue, queryField string,
	globalValue, globalField string,
	fallbackField string,
) string {
	if queryValue != "" {
		return queryValue
	}
	if queryField != "" {
		if v := fieldString(fields, queryField); v != "" {
			return v
		}
	}
	if globalValue != "" {
		return globalValue
	}
	if globalField != "" {
		if v := fieldString(fields, globalField); v != "" {
			return v
		}
	}
	return fieldString(fields, fallbackField)
}

// fieldString extracts a field from the event map as a string.
// Non-string values are converted with %v formatting.
func fieldString(fields map[string]interface{}, key string) string {
	v, ok := fields[key]
	if !ok {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprintf("%v", v)
}

// ─── project helpers ──────────────────────────────────────────────────────────

func (s *Service) createProjectIfNotExist() bool {
	if s.isProjectExist() {
		return true
	}
	return s.createProject()
}

func (s *Service) isProjectExist() bool {
	logrus.Infof("Checking if project '%s' exists in InsightFinder", s.ProjectName)

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", s.config.UserName)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", s.ProjectName)
	form.Add("systemName", s.SystemName)

	endpoint := s.config.ServerURL + projectEndpoint
	req, err := http.NewRequest("POST", endpoint, bytes.NewBufferString(form.Encode()))
	if err != nil {
		logrus.Errorf("isProjectExist: %v", err)
		return false
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		logrus.Errorf("isProjectExist request: %v", err)
		return false
	}
	defer resp.Body.Close()

	var checkResp CheckAndAddCustomProjectResponse
	if err := json.NewDecoder(resp.Body).Decode(&checkResp); err != nil {
		logrus.Errorf("isProjectExist decode: %v", err)
		return false
	}

	if checkResp.IsSuccess {
		if checkResp.IsProjectExist {
			logrus.Infof("Project '%s' exists", s.ProjectName)
			return true
		}
		logrus.Infof("Project '%s' does not exist", s.ProjectName)
		return false
	}
	logrus.Errorf("Project check failed: %s", checkResp.Message)
	return false
}

func (s *Service) createProject() bool {
	logrus.Infof("Creating project '%s' in InsightFinder", s.ProjectName)

	request := CheckAndAddCustomProjectRequest{
		Operation:        "create",
		UserName:         s.config.UserName,
		LicenseKey:       s.config.LicenseKey,
		ProjectName:      s.ProjectName,
		SystemName:       s.SystemName,
		InstanceType:     s.InstanceType,
		ProjectCloudType: s.CloudType,
		DataType:         s.DataType,
		InsightAgentType: s.InsightAgentType,
		SamplingInterval: int(s.SamplingInterval),
	}

	// Build URL query params (same fields as body, matching loki-agent pattern).
	params := url.Values{}
	params.Set("operation", request.Operation)
	params.Set("userName", request.UserName)
	params.Set("licenseKey", request.LicenseKey)
	params.Set("projectName", request.ProjectName)
	params.Set("systemName", request.SystemName)
	params.Set("instanceType", request.InstanceType)
	params.Set("projectCloudType", request.ProjectCloudType)
	params.Set("dataType", request.DataType)
	params.Set("insightAgentType", request.InsightAgentType)
	params.Set("samplingInterval", fmt.Sprintf("%d", request.SamplingInterval))

	jsonBody, err := json.Marshal(request)
	if err != nil {
		logrus.Errorf("createProject marshal: %v", err)
		return false
	}

	endpoint := s.config.ServerURL + projectEndpoint + "?" + params.Encode()
	req, err := http.NewRequest("POST", endpoint, bytes.NewBuffer(jsonBody))
	if err != nil {
		logrus.Errorf("createProject: %v", err)
		return false
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("agent-type", "Stream")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		logrus.Errorf("createProject request: %v", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		logrus.Infof("Project '%s' created successfully", s.ProjectName)
		return true
	}
	body := make([]byte, 512)
	n, _ := resp.Body.Read(body)
	logrus.Errorf("createProject status %d: %s", resp.StatusCode, string(body[:n]))
	return false
}
