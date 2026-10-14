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
		ProjectType:         "LOG",
		Container:           ifConfig.IsContainer,
		CloudType:           ifConfig.CloudType,
		InstanceType:        ifConfig.InstanceType,
		SamplingInterval:    uint(ifConfig.SamplingInterval),
		defaultInstanceName: lokiConfig.DefaultInstanceNameField,
		projects:            make(map[string]bool),
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

	// Set default values
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

// Initialize initializes the InsightFinder service and creates the project of
// every enabled query if needed, so a bad project config fails at startup.
func (s *Service) Initialize(queries []config.QueryConfig) error {
	logrus.Info("Initializing InsightFinder service...")

	for _, q := range queries {
		if !q.Enabled {
			continue
		}
		if err := s.EnsureProject(q.ProjectName, q.SystemName); err != nil {
			return fmt.Errorf("query '%s': %w", q.Name, err)
		}
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

// ConvertToLogData converts LogEntry slice to InsightFinder LogData slice using the query config.
// The result is in the exact format expected by SendLogDataInternal / the IF API.
func (s *Service) ConvertToLogData(entries []models.LogEntry, queryConfig config.QueryConfig) []LogData {
	logDataList := make([]LogData, 0, len(entries))

	for _, entry := range entries {
		timestamp := entry.Timestamp.UnixMilli()

		instanceFieldName := s.defaultInstanceName
		if queryConfig.InstanceNameField != "" {
			instanceFieldName = queryConfig.InstanceNameField
		}

		var tag string
		if instanceFieldName != "" {
			tag = s.getFieldValueFromEntry(entry, instanceFieldName)
			if queryConfig.ContainerNameField != "" {
				containerValue := s.getFieldValueFromEntry(entry, queryConfig.ContainerNameField)
				if containerValue != "" && tag != "" {
					tag = CleanDeviceName(containerValue) + "_" + CleanDeviceName(tag)
				}
			}
		}

		componentName := ""
		if queryConfig.ComponentNameField != "" {
			componentName = s.getFieldValueFromEntry(entry, queryConfig.ComponentNameField)
			if componentName != "" {
				componentName = CleanDeviceName(componentName)
			}
		}

		logDataList = append(logDataList, LogData{
			TimeStamp:     timestamp,
			Tag:           tag,
			Data:          entry.Message,
			ComponentName: componentName,
			ProjectName:   queryConfig.ProjectName,
			SystemName:    queryConfig.SystemName,
		})
	}

	return logDataList
}

// SendLogData converts log entries and sends them to InsightFinder.
func (s *Service) SendLogData(entries []models.LogEntry, queryConfig config.QueryConfig) (*SendLogDataResult, error) {
	startTime := time.Now()

	if len(entries) == 0 {
		return &SendLogDataResult{TimeTaken: time.Since(startTime)}, nil
	}

	logDataList := s.ConvertToLogData(entries, queryConfig)

	totalBytes := 0
	for _, entry := range entries {
		totalBytes += len(entry.Message)
	}

	if err := s.SendLogDataInternal(queryConfig.ProjectName, queryConfig.SystemName, logDataList); err != nil {
		return nil, err
	}

	return &SendLogDataResult{
		EntriesSent: len(entries),
		BytesSent:   totalBytes,
		TimeTaken:   time.Since(startTime),
	}, nil
}

// EnsureProject creates the project if it doesn't exist. Projects that were
// verified once are cached, so calling this before every send is cheap.
func (s *Service) EnsureProject(projectName, systemName string) error {
	if projectName == "" {
		return fmt.Errorf("project name is empty")
	}

	s.projectsMu.Lock()
	defer s.projectsMu.Unlock()
	if s.projects[projectName] {
		return nil
	}

	if !s.IsProjectExist(projectName, systemName) && !s.CreateProject(projectName, systemName) {
		return fmt.Errorf("failed to create or verify project: %s", projectName)
	}
	s.projects[projectName] = true
	return nil
}

// IsProjectExist checks if project exists
func (s *Service) IsProjectExist(projectName, systemName string) bool {
	logrus.Infof("Checking if project '%s' exists in InsightFinder", projectName)

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", s.config.UserName)
	form.Add("licenseKey", s.config.LicenseKey)
	form.Add("projectName", projectName)
	form.Add("systemName", systemName)

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
			logrus.Infof("Project '%s' exists in InsightFinder", projectName)
			return true
		}
		logrus.Infof("Project '%s' does not exist in InsightFinder", projectName)
		return false
	}

	logrus.Errorf("Project check failed: %s", checkResponse.Message)
	return false
}

// CreateProject creates a new project
func (s *Service) CreateProject(projectName, systemName string) bool {
	logrus.Infof("Creating project '%s' in InsightFinder", projectName)

	request := CheckAndAddCustomProjectRequest{
		Operation:        "create",
		UserName:         s.config.UserName,
		LicenseKey:       s.config.LicenseKey,
		ProjectName:      projectName,
		SystemName:       systemName,
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

	logrus.Infof("Project '%s' created successfully in InsightFinder", projectName)
	return true
}

// getFieldValueFromEntry extracts the field value from LogEntry based on the specified field name
func (s *Service) getFieldValueFromEntry(entry models.LogEntry, fieldName string) string {
	// Check the Labels map for the field - all fields are now stored here dynamically
	if value, exists := entry.Labels[fieldName]; exists {
		return value
	}

	// Return empty string if field not found
	return ""
}

// SendLogDataInternal sends LogData to the given project using the send_logs.go
// implementation, creating the project first if it doesn't exist yet.
func (s *Service) SendLogDataInternal(projectName, systemName string, logEntries []LogData) error {
	if len(logEntries) == 0 {
		return nil
	}
	if err := s.EnsureProject(projectName, systemName); err != nil {
		return err
	}
	return s.SendLogDataBasic(projectName, logEntries)
}
