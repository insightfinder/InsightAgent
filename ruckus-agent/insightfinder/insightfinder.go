package insightfinder

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/carlmjohnson/requests"
	"github.com/google/go-querystring/query"
	config "github.com/insightfinder/ruckus-agent/configs"
	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

const (
	METRIC_DATA_API     = "/api/v2/metric-data-receive"
	LOG_DATA_API        = "/api/v1/customprojectrawdata"
	PROJECT_ENDPOINT    = "/api/v1/check-and-add-custom-project"
	LOG_DATA_AGENT_TYPE = "Stream"
	CHUNK_SIZE          = 2 * 1024 * 1024 // 2MB
	MAX_PACKET_SIZE     = 10000000        // 10MB
	HTTP_RETRY_TIMES    = 3
	HTTP_RETRY_INTERVAL = 5 // seconds
)

func NewService(config config.InsightFinderConfig) *Service {
	// Create HTTP client with timeout and TLS settings
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}

	client := &http.Client{
		Transport: tr,
		Timeout:   180 * time.Second,
	}

	service := &Service{
		config:      config,
		httpClient:  client,
		ProjectName: config.ProjectName,
		SystemName:  config.SystemName,
		ProjectType: "Metric", // Default for Ruckus metrics
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
	if s.config.UserName == "" {
		logrus.Error("UserName is required")
		return false
	}
	if s.config.LicenseKey == "" {
		logrus.Error("LicenseKey is required")
		return false
	}
	if s.config.ProjectName == "" {
		logrus.Error("ProjectName is required")
		return false
	}

	// Set defaults for missing fields
	if s.SystemName == "" {
		s.SystemName = s.ProjectName
		logrus.Warnf("SystemName not set, defaulting to ProjectName: %s", s.ProjectName)
	}

	if s.CloudType == "" {
		if s.config.CloudType != "" {
			s.CloudType = s.config.CloudType
		} else {
			s.CloudType = "OnPremise"
			logrus.Warn("CloudType not set, defaulting to OnPremise")
		}
	}

	if s.InstanceType == "" {
		if s.config.InstanceType != "" {
			s.InstanceType = s.config.InstanceType
		} else {
			s.InstanceType = "OnPremise"
			logrus.Warn("InstanceType not set, defaulting to OnPremise")
		}
	}

	// Set ProjectType from config or default
	if s.config.ProjectType != "" {
		s.ProjectType = s.config.ProjectType
	}

	// Set DataType based on ProjectType
	s.DataType = s.ProjectType

	// Set default sampling interval (from config or default to 5 minutes)
	if s.config.SamplingInterval > 0 {
		s.SamplingInterval = uint(s.config.SamplingInterval)
	} else {
		s.SamplingInterval = 5 * 60 // 5 minutes default
	}

	// Set InsightAgentType based on ProjectType and Container settings
	if s.ProjectType == "Metric" {
		if s.Container {
			s.InsightAgentType = "containerStreaming"
		} else {
			s.InsightAgentType = "RuckusAgent" // Custom agent type for Ruckus
		}
	} else {
		if s.Container {
			s.InsightAgentType = "ContainerCustom"
		} else {
			s.InsightAgentType = "RuckusAgent"
		}
	}

	logrus.Infof("InsightFinder configuration validated successfully:")
	logrus.Infof("  Project: %s", s.ProjectName)
	logrus.Infof("  System: %s", s.SystemName)
	logrus.Infof("  CloudType: %s", s.CloudType)
	logrus.Infof("  AgentType: %s", s.InsightAgentType)
	logrus.Infof("  SamplingInterval: %d seconds", s.SamplingInterval)

	return true
}

// Create project if it doesn't exist
func (s *Service) CreateProjectIfNotExist() bool {
	if !s.IsProjectExist() {
		return s.CreateProject()
	}
	return true
}

// Check if project exists
func (s *Service) IsProjectExist() bool {
	logrus.Infof("Checking if project '%s' exists in InsightFinder", s.ProjectName)

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", s.config.UserName)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", s.ProjectName)
	form.Add("systemName", s.SystemName)

	url := fmt.Sprintf("%s%s", s.config.ServerURL, PROJECT_ENDPOINT)

	req, err := http.NewRequest("POST", url, bytes.NewBufferString(form.Encode()))
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

	if checkResponse.IsSuccess {
		if checkResponse.IsProjectExist {
			logrus.Infof("Project '%s' exists in InsightFinder", s.ProjectName)
			return true
		}
		logrus.Infof("Project '%s' does not exist in InsightFinder", s.ProjectName)
		return false
	}

	logrus.Errorf("Project check failed: %s", checkResponse.Message)
	return false
}

// Create new project
func (s *Service) CreateProject() bool {
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
	requestForm, err := query.Values(request)
	if err != nil {
		logrus.Errorf("Error building request form to create project: %v", err)
		return false
	}

	var resultStr string
	err = requests.URL(s.config.ServerURL).Path(PROJECT_ENDPOINT).Header("agent-type", "Stream").BodyJSON(request).Params(requestForm).ToString(&resultStr).Post().Fetch(context.Background())
	if err != nil {
		logrus.Errorf("Failed to create project: %v", err)
		return false
	}

	logrus.Infof("Project '%s' created successfully in InsightFinder", s.ProjectName)
	return true
}

// Send metrics in bulk - most efficient for large datasets
func (s *Service) SendMetricsBulk(metrics []models.MetricData) error {
	if len(metrics) == 0 {
		return nil
	}

	logrus.Infof("Sending %d metrics in bulk to InsightFinder using v2 API", len(metrics))

	// Group metrics by instance and timestamp
	instanceDataMap := make(map[string]InstanceData)
	var minTimestamp, maxTimestamp int64

	for i, metric := range metrics {
		instanceName := metric.InstanceName
		timestamp := metric.Timestamp

		// Convert timestamp to epoch milliseconds if it's in seconds
		if timestamp < 1e12 {
			timestamp = timestamp * 1000
		}

		// Track min/max timestamps
		if i == 0 {
			minTimestamp = timestamp
			maxTimestamp = timestamp
		} else {
			if timestamp < minTimestamp {
				minTimestamp = timestamp
			}
			if timestamp > maxTimestamp {
				maxTimestamp = timestamp
			}
		}

		// Get or create instance data
		instanceData, exists := instanceDataMap[instanceName]
		if !exists {
			instanceData = InstanceData{
				InstanceName:       instanceName,
				ComponentName:      instanceName,
				DataInTimestampMap: make(map[int64]DataInTimestamp),
			}
		}

		// Create metric data points
		metricDataPoints := make([]MetricDataPoint, 0)
		dataInTimestamp := DataInTimestamp{
			TimeStamp:        timestamp,
			MetricDataPoints: &metricDataPoints,
		}

		// Add all metric data points for this AP
		for metricName, value := range metric.Data {
			if floatValue, ok := convertToFloat64(value); ok {
				*dataInTimestamp.MetricDataPoints = append(*dataInTimestamp.MetricDataPoints, MetricDataPoint{
					MetricName: metricName,
					Value:      floatValue,
				})
			} else {
				logrus.Debugf("Skipping non-numeric metric %s: %v (type: %T)", metricName, value, value)
			}
		}

		instanceData.Zone = metric.Zone
		instanceData.DataInTimestampMap[timestamp] = dataInTimestamp
		instanceDataMap[instanceName] = instanceData
	}

	// Create payload using the v2 API format
	payload := IFMetricPostRequestPayload{
		LicenseKey: s.config.LicenseKey,
		UserName:   s.config.UserName,
		Data: MetricDataReceivePayload{
			ProjectName:      s.ProjectName,
			UserName:         s.config.UserName,
			SystemName:       s.SystemName,
			InstanceDataMap:  instanceDataMap,
			MinTimestamp:     minTimestamp,
			MaxTimestamp:     maxTimestamp,
			InsightAgentType: s.InsightAgentType,
			SamplingInterval: strconv.Itoa(int(s.SamplingInterval)),
			CloudType:        s.CloudType,
		},
	}

	return s.sendMetricPayloadV2(payload)
}

// Send metrics in streaming chunks - memory efficient
func (s *Service) SendMetricsStreaming(metrics []models.MetricData, chunkSize int) error {
	if len(metrics) == 0 {
		return nil
	}

	logrus.Infof("Sending %d metrics in streaming chunks of %d", len(metrics), chunkSize)

	for i := 0; i < len(metrics); i += chunkSize {
		end := i + chunkSize
		if end > len(metrics) {
			end = len(metrics)
		}

		chunk := metrics[i:end]
		logrus.Debugf("Sending chunk %d/%d (%d metrics)", (i/chunkSize)+1, (len(metrics)+chunkSize-1)/chunkSize, len(chunk))

		if err := s.SendMetricsBulk(chunk); err != nil {
			return fmt.Errorf("failed to send chunk %d: %v", (i/chunkSize)+1, err)
		}

		// Small delay between chunks
		if end < len(metrics) {
			time.Sleep(100 * time.Millisecond)
		}
	}

	return nil
}

// Send individual metrics - for backward compatibility
func (s *Service) SendMetrics(metrics []models.MetricData) error {
	return s.SendMetricsBulk(metrics)
}

// Send metric payload to InsightFinder v2 API
func (s *Service) sendMetricPayloadV2(payload IFMetricPostRequestPayload) error {
	url := fmt.Sprintf("%s%s", s.config.ServerURL, METRIC_DATA_API)

	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal metrics payload: %v", err)
	}

	if len(jsonPayload) > MAX_PACKET_SIZE {
		return fmt.Errorf("payload size (%d bytes) exceeds maximum allowed (%d bytes)", len(jsonPayload), MAX_PACKET_SIZE)
	}

	logrus.Debugf("Sending %d bytes to InsightFinder v2 API", len(jsonPayload))

	// Send with retry logic
	var lastErr error
	for attempt := 1; attempt <= HTTP_RETRY_TIMES; attempt++ {
		req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonPayload))
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
			logrus.Infof("Successfully sent metrics to InsightFinder v2 API (instances: %d)", len(payload.Data.InstanceDataMap))
			return nil
		} else {
			bodyBytes := make([]byte, 1024)
			n, _ := resp.Body.Read(bodyBytes)
			lastErr = fmt.Errorf("request failed with status: %d, body: %s", resp.StatusCode, string(bodyBytes[:n]))
			logrus.Warnf("Attempt %d/%d failed with status %d", attempt, HTTP_RETRY_TIMES, resp.StatusCode)
			if attempt < HTTP_RETRY_TIMES {
				time.Sleep(time.Duration(HTTP_RETRY_INTERVAL) * time.Second)
				continue
			}
		}
	}

	return fmt.Errorf("failed to send metrics after %d attempts: %v", HTTP_RETRY_TIMES, lastErr)
}

// Get configuration
func (s *Service) GetConfig() config.InsightFinderConfig {
	return s.config
}
