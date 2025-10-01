package insightfinder

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"

	"github.com/carlmjohnson/requests"
	"github.com/google/go-querystring/query"
	config "github.com/insightfinder/loki-agent/configs"
	"github.com/insightfinder/loki-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

const (
	LOG_DATA_API        = "/api/v1/customprojectrawdata"
	PROJECT_ENDPOINT    = "/api/v1/check-and-add-custom-project"
	LOG_DATA_AGENT_TYPE = "Stream"
	CHUNK_SIZE          = 2 * 1024 * 1024 // 2MB
	MAX_PACKET_SIZE     = 10000000        // 10MB
	HTTP_RETRY_TIMES    = 3
	HTTP_RETRY_INTERVAL = 5 // seconds
)

func NewService(ifConfig config.InsightFinderConfig, lokiConfig config.LokiConfig) *Service {
	// Create HTTP client with timeout and TLS settings
	tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}
	client := &http.Client{Transport: tr, Timeout: 180 * time.Second}

	service := &Service{
		config:              ifConfig,
		httpClient:          client,
		ProjectName:         ifConfig.LogsProjectName,
		LogProjectName:      ifConfig.LogsProjectName,
		SystemName:          ifConfig.LogsSystemName,
		ProjectType:         "LOG",
		Container:           ifConfig.IsContainer,
		CloudType:           ifConfig.CloudType,
		InstanceType:        ifConfig.InstanceType,
		SamplingInterval:    uint(ifConfig.SamplingInterval),
		defaultInstanceName: lokiConfig.DefaultInstanceNameField,
	}

	// Validate and set defaults
	service.Validate()
	return service
}

// updateDerivedTypes updates DataType and InsightAgentType for log data
func (s *Service) updateDerivedTypes() {
	s.DataType = "Log"
	if s.Container {
		s.InsightAgentType = "ContainerCustom"
	} else {
		s.InsightAgentType = "Custom"
	}
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
	if s.config.LogsProjectName == "" {
		logrus.Error("LogsProjectName is required")
		return false
	}

	// Set default values
	if s.ProjectName == "" {
		s.ProjectName = s.config.LogsProjectName
	}
	if s.LogProjectName == "" {
		s.LogProjectName = s.config.LogsProjectName
	}
	if s.SystemName == "" {
		s.SystemName = s.config.LogsSystemName
	}
	if s.ProjectType == "" {
		s.ProjectType = "LOG"
	}

	// Update derived types
	s.updateDerivedTypes()

	logrus.Info("InsightFinder configuration validated successfully")
	return true
}

// GetConfig returns the configuration
func (s *Service) GetConfig() config.InsightFinderConfig {
	return s.config
}

// Initialize initializes the InsightFinder service and creates projects if needed
func (s *Service) Initialize() error {
	logrus.Info("Initializing InsightFinder service...")

	// Create project if it doesn't exist
	if err := s.CreateLogsProjectIfNotExist(); err != nil {
		return fmt.Errorf("failed to create logs project: %w", err)
	}

	logrus.Info("InsightFinder service initialized successfully")
	return nil
}

// SendLogDataResult represents the result of sending log data
type SendLogDataResult struct {
	EntriesSent int
	BytesSent   int
	TimeTaken   time.Duration
}

// SendLogDataWithLabels sends log entries to InsightFinder with labels metadata
// This is the method expected by the worker
func (s *Service) SendLogData(entries []models.LogEntry, queryConfig config.QueryConfig) (*SendLogDataResult, error) {
	startTime := time.Now()

	if len(entries) == 0 {
		return &SendLogDataResult{
			EntriesSent: 0,
			BytesSent:   0,
			TimeTaken:   time.Since(startTime),
		}, nil
	}

	// Convert models.LogEntry to insightfinder.LogData
	logDataList := make([]LogData, 0, len(entries))
	totalBytes := 0

	for _, entry := range entries {
		// Convert timestamp to Unix timestamp in milliseconds
		timestamp := entry.Timestamp.UnixMilli()

		// Get tag value based on configured default instance name field or query override
		instanceFieldName := s.defaultInstanceName
		if queryConfig.InstanceNameField != "" {
			instanceFieldName = queryConfig.InstanceNameField
		}

		// Skip tag creation if no instance field is configured
		var tag string
		if instanceFieldName != "" {
			tag = s.getFieldValueFromEntry(entry, instanceFieldName)

			// If container name field is specified in query config, append its value to tag
			if queryConfig.ContainerNameField != "" {
				containerValue := s.getFieldValueFromEntry(entry, queryConfig.ContainerNameField)
				if containerValue != "" {
					if tag != "" {
						tag = CleanDeviceName(containerValue) + "_" + CleanDeviceName(tag)
					}
				}
			}
		}

		// Get component name from query config field (don't set if empty)
		componentName := ""
		if queryConfig.ComponentNameField != "" {
			componentName = s.getFieldValueFromEntry(entry, queryConfig.ComponentNameField)
			if componentName != "" {
				componentName = CleanDeviceName(componentName)
			}
		}

		// Create log data entry
		logData := LogData{
			TimeStamp:     timestamp,
			Tag:           tag,
			Data:          entry.Message,
			ComponentName: componentName,
		}

		logDataList = append(logDataList, logData)
		totalBytes += len(entry.Message)
	}

	// Send the data using the existing SendLogDataInternal method
	err := s.SendLogDataInternal(logDataList)
	if err != nil {
		return nil, err
	}

	return &SendLogDataResult{
		EntriesSent: len(entries),
		BytesSent:   totalBytes,
		TimeTaken:   time.Since(startTime),
	}, nil
}

// CreateLogsProjectIfNotExist creates the logs project if it doesn't exist
func (s *Service) CreateLogsProjectIfNotExist() error {
	// Temporarily switch to logs project settings
	originalProjectName := s.ProjectName
	originalSystemName := s.SystemName
	originalProjectType := s.ProjectType

	s.ProjectName = s.config.LogsProjectName
	s.SystemName = s.config.LogsSystemName
	s.ProjectType = s.config.LogsProjectType
	s.updateDerivedTypes()

	result := s.CreateProjectIfNotExist()

	// Restore original settings
	s.ProjectName = originalProjectName
	s.SystemName = originalSystemName
	s.ProjectType = originalProjectType
	s.updateDerivedTypes()

	if !result {
		return fmt.Errorf("failed to create or verify logs project: %s", s.config.LogsProjectName)
	}
	return nil
}

// CreateProjectIfNotExist creates the project if it doesn't exist
func (s *Service) CreateProjectIfNotExist() bool {
	if !s.IsProjectExist() {
		return s.CreateProject()
	}
	return true
}

// IsProjectExist checks if project exists
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

// CreateProject creates a new project
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

// getFieldValueFromEntry extracts the field value from LogEntry based on the specified field name
func (s *Service) getFieldValueFromEntry(entry models.LogEntry, fieldName string) string {
	switch fieldName {
	case "container":
		return entry.Stream.Container
	case "instance":
		return entry.Stream.Instance
	case "node_name":
		return entry.Stream.Node
	case "pod":
		return entry.Stream.Pod
	case "app":
		return entry.Stream.App
	default:
		// Return empty string for invalid field names
		return ""
	}
}

// SendLogDataInternal sends LogData using the send_logs.go implementation
func (s *Service) SendLogDataInternal(logEntries []LogData) error {
	return s.SendLogDataBasic(logEntries)
}
