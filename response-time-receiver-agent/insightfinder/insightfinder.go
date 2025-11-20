package insightfinder

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/insightfinder/receiver-agent/configs"
	"github.com/sirupsen/logrus"
)

const (
	METRIC_DATA_API     = "/api/v2/metric-data-receive"
	PROJECT_ENDPOINT    = "/api/v1/check-and-add-custom-project"
	CHUNK_SIZE          = 2 * 1024 * 1024 // 2MB
	MAX_PACKET_SIZE     = 10000000        // 10MB
	HTTP_RETRY_TIMES    = 3
	HTTP_RETRY_INTERVAL = 5 // seconds
)

// NewService creates a new InsightFinder service instance
func NewService(config configs.InsightFinderConfig) *Service {
	// Create HTTP client with timeout and TLS settings
	tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}
	client := &http.Client{Transport: tr, Timeout: 180 * time.Second}

	service := &Service{
		config:      config,
		httpClient:  client,
		ProjectName: config.MetricsProjectName,
		SystemName:  config.MetricsSystemName,
		ProjectType: "Metric",
		Container:   config.IsContainer,
	}

	// Validate and set defaults
	service.Validate()
	return service
}

// Validate configuration and set defaults
func (s *Service) Validate() bool {
	logrus.Info("Validating InsightFinder configuration...")

	if s.config.ServerURL == "" {
		logrus.Error("ServerURL is required")
		return false
	}
	if s.config.Username == "" {
		logrus.Error("Username is required")
		return false
	}
	if s.config.LicenseKey == "" {
		logrus.Error("LicenseKey is required")
		return false
	}
	if s.config.MetricsProjectName == "" {
		logrus.Error("MetricsProjectName is required")
		return false
	}

	// Set defaults
	if s.SystemName == "" {
		s.SystemName = s.ProjectName
	}

	if s.CloudType == "" {
		if s.config.CloudType != "" {
			s.CloudType = s.config.CloudType
		} else {
			s.CloudType = "OnPremise"
		}
	}

	if s.InstanceType == "" {
		if s.config.InstanceType != "" {
			s.InstanceType = s.config.InstanceType
		} else {
			s.InstanceType = "OnPremise"
		}
	}

	if s.ProjectType == "" {
		s.ProjectType = "Metric"
	}

	// Set sampling interval
	if s.config.SamplingInterval > 0 {
		s.SamplingInterval = uint(s.config.SamplingInterval)
	} else {
		s.SamplingInterval = 60
	}

	// Set DataType and InsightAgentType
	s.updateDerivedTypes()

	logrus.Infof("InsightFinder configuration validated successfully")
	logrus.Infof("  Project: %s", s.ProjectName)
	logrus.Infof("  System: %s", s.SystemName)
	logrus.Infof("  AgentType: %s", s.InsightAgentType)

	return true
}

// updateDerivedTypes updates DataType and InsightAgentType based on ProjectType
func (s *Service) updateDerivedTypes() {
	switch s.ProjectType {
	case "Metric", "METRIC":
		s.DataType = "Metric"
		if s.Container {
			s.InsightAgentType = "containerStreaming"
		} else {
			s.InsightAgentType = "ReceiverAgent"
		}
	default:
		s.DataType = s.ProjectType
		if s.Container {
			s.InsightAgentType = "ContainerCustom"
		} else {
			s.InsightAgentType = "Custom"
		}
	}
}

// CreateProjectIfNotExist creates project if it doesn't exist
func (s *Service) CreateProjectIfNotExist() bool {
	if !s.IsProjectExist() {
		return s.CreateProject()
	}
	return true
}

// IsProjectExist checks if project exists
func (s *Service) IsProjectExist() bool {
	logrus.Infof("Checking if project '%s' exists", s.ProjectName)

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", s.config.Username)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", s.ProjectName)
	form.Add("systemName", s.SystemName)

	apiURL := fmt.Sprintf("%s%s", s.config.ServerURL, PROJECT_ENDPOINT)

	req, err := http.NewRequest("POST", apiURL, bytes.NewBufferString(form.Encode()))
	if err != nil {
		logrus.Errorf("Failed to create project check request: %v", err)
		return false
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		logrus.Errorf("Failed to check project existence: %v", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		logrus.Errorf("Project check failed with status: %d", resp.StatusCode)
		return false
	}

	var checkResponse CheckAndAddCustomProjectResponse
	if err := json.NewDecoder(resp.Body).Decode(&checkResponse); err != nil {
		logrus.Errorf("Failed to decode project check response: %v", err)
		return false
	}

	return checkResponse.IsSuccess && checkResponse.IsProjectExist
}

// CreateProject creates a new project
func (s *Service) CreateProject() bool {
	logrus.Infof("Creating project '%s'", s.ProjectName)

	form := url.Values{}
	form.Add("operation", "create")
	form.Add("userName", s.config.Username)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", s.ProjectName)
	form.Add("systemName", s.SystemName)
	form.Add("instanceType", s.InstanceType)
	form.Add("projectCloudType", s.CloudType)
	form.Add("dataType", s.DataType)
	form.Add("insightAgentType", s.InsightAgentType)
	form.Add("samplingInterval", strconv.Itoa(int(s.SamplingInterval)))

	apiURL := fmt.Sprintf("%s%s", s.config.ServerURL, PROJECT_ENDPOINT)

	req, err := http.NewRequest("POST", apiURL, bytes.NewBufferString(form.Encode()))
	if err != nil {
		logrus.Errorf("Failed to create project request: %v", err)
		return false
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		logrus.Errorf("Failed to create project: %v", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		logrus.Infof("Project '%s' created successfully", s.ProjectName)
		return true
	}

	logrus.Errorf("Project creation failed with status: %d", resp.StatusCode)
	return false
}

// SendMetrics sends metrics to InsightFinder
func (s *Service) SendMetrics(instanceName string, timestamp int64, metrics map[string]float64) error {
	if len(metrics) == 0 {
		return nil
	}

	logrus.Infof("Sending %d metrics to InsightFinder for instance: %s", len(metrics), instanceName)

	// Align timestamp to sampling interval
	alignedTimestamp := alignTimestamp(timestamp, int(s.SamplingInterval))

	// Create metric data points
	metricDataPoints := make([]MetricDataPoint, 0, len(metrics))
	for metricName, value := range metrics {
		metricDataPoints = append(metricDataPoints, MetricDataPoint{
			MetricName: metricName,
			Value:      value,
		})
	}

	// Create data structure
	dataInTimestamp := DataInTimestamp{
		TimeStamp:        alignedTimestamp,
		MetricDataPoints: &metricDataPoints,
	}

	instanceData := InstanceData{
		InstanceName:       instanceName,
		ComponentName:      s.SystemName,
		DataInTimestampMap: map[int64]DataInTimestamp{alignedTimestamp: dataInTimestamp},
	}

	instanceDataMap := map[string]InstanceData{instanceName: instanceData}

	// Create payload
	payload := IFMetricPostRequestPayload{
		LicenseKey: s.config.LicenseKey,
		UserName:   s.config.Username,
		Data: MetricDataReceivePayload{
			ProjectName:      s.ProjectName,
			UserName:         s.config.Username,
			SystemName:       s.SystemName,
			InstanceDataMap:  instanceDataMap,
			MinTimestamp:     alignedTimestamp,
			MaxTimestamp:     alignedTimestamp,
			InsightAgentType: s.InsightAgentType,
			SamplingInterval: strconv.Itoa(int(s.SamplingInterval)),
			CloudType:        s.CloudType,
		},
	}

	return s.sendMetricPayload(payload)
}

// sendMetricPayload sends the metric payload to InsightFinder
func (s *Service) sendMetricPayload(payload IFMetricPostRequestPayload) error {
	apiURL := fmt.Sprintf("%s%s", s.config.ServerURL, METRIC_DATA_API)

	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal metrics payload: %v", err)
	}

	if len(jsonPayload) > MAX_PACKET_SIZE {
		return fmt.Errorf("payload size (%d bytes) exceeds maximum allowed (%d bytes)", len(jsonPayload), MAX_PACKET_SIZE)
	}

	logrus.Debugf("Sending %d bytes to InsightFinder", len(jsonPayload))

	// Send with retry logic
	var lastErr error
	for attempt := 1; attempt <= HTTP_RETRY_TIMES; attempt++ {
		req, err := http.NewRequest("POST", apiURL, bytes.NewBuffer(jsonPayload))
		if err != nil {
			return fmt.Errorf("failed to create request: %v", err)
		}

		req.Header.Set("Content-Type", "application/json")

		resp, err := s.httpClient.Do(req)
		if err != nil {
			lastErr = err
			logrus.Warnf("Attempt %d/%d failed: %v", attempt, HTTP_RETRY_TIMES, err)
			if attempt < HTTP_RETRY_TIMES {
				time.Sleep(time.Duration(HTTP_RETRY_INTERVAL) * time.Second)
				continue
			}
			return fmt.Errorf("failed to send metrics after %d attempts: %v", HTTP_RETRY_TIMES, err)
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			logrus.Infof("Successfully sent metrics to InsightFinder")
			return nil
		}

		bodyBytes := make([]byte, 1024)
		n, _ := resp.Body.Read(bodyBytes)
		lastErr = fmt.Errorf("request failed with status: %d, body: %s", resp.StatusCode, string(bodyBytes[:n]))
		logrus.Warnf("Attempt %d/%d failed with status %d", attempt, HTTP_RETRY_TIMES, resp.StatusCode)

		if attempt < HTTP_RETRY_TIMES {
			time.Sleep(time.Duration(HTTP_RETRY_INTERVAL) * time.Second)
		}
	}

	return fmt.Errorf("failed to send metrics after %d attempts: %v", HTTP_RETRY_TIMES, lastErr)
}

// alignTimestamp aligns timestamp to the sampling interval
func alignTimestamp(timestamp int64, samplingInterval int) int64 {
	// Convert to seconds if in milliseconds
	if timestamp > 1e12 {
		timestamp = timestamp / 1000
	}

	// Align to sampling interval
	aligned := (timestamp / int64(samplingInterval)) * int64(samplingInterval)

	// Convert back to milliseconds
	return aligned * 1000
}
