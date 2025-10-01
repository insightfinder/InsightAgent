package config

import (
	"fmt"
	"os"
	"time"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v2"
)

// LoadConfig loads configuration from YAML file
func LoadConfig(configPath string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", configPath)

	// Check if file exists
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("configuration file does not exist: %s", configPath)
	}

	// Read YAML file
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read YAML file: %v", err)
	}

	var config Config

	// Parse YAML
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse YAML file: %v", err)
	}

	// Validate and set defaults
	setDefaults(&config)
	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %v", err)
	}

	logrus.Info("Configuration loaded successfully")
	return &config, nil
}

// setDefaults sets default values for configuration fields if they are not provided
func setDefaults(config *Config) {
	// Agent defaults
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "INFO"
	}
	if config.Agent.DataFormat == "" {
		config.Agent.DataFormat = "json"
	}
	if config.Agent.Timezone == "" {
		config.Agent.Timezone = "UTC"
	}

	// Loki defaults
	if config.Loki.MaxConcurrentRequests == 0 {
		config.Loki.MaxConcurrentRequests = 10
	}
	if config.Loki.MaxRetries == 0 {
		config.Loki.MaxRetries = 3
	}
	if config.Loki.QueryTimeout == 0 {
		config.Loki.QueryTimeout = 60 // 60 seconds
	}
	if config.Loki.MaxEntriesPerQuery == 0 {
		config.Loki.MaxEntriesPerQuery = 1000
	}
	// Note: Query interval and time ranges are determined by InsightFinder.SamplingInterval

	// InsightFinder defaults
	if config.InsightFinder.ServerURL == "" {
		config.InsightFinder.ServerURL = "https://app.insightfinder.com"
	}
	if config.InsightFinder.LogsProjectType == "" {
		config.InsightFinder.LogsProjectType = "LOG"
	}
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 60
	}
	if config.InsightFinder.CloudType == "" {
		config.InsightFinder.CloudType = "OnPremise"
	}
	if config.InsightFinder.InstanceType == "" {
		config.InsightFinder.InstanceType = "OnPremise"
	}
	if config.InsightFinder.ChunkSize == 0 {
		config.InsightFinder.ChunkSize = 2 * 1024 * 1024 // 2MB
	}
	if config.InsightFinder.MaxPacketSize == 0 {
		config.InsightFinder.MaxPacketSize = 10 * 1024 * 1024 // 10MB
	}
	if config.InsightFinder.RetryTimes == 0 {
		config.InsightFinder.RetryTimes = 3
	}
	if config.InsightFinder.RetryInterval == 0 {
		config.InsightFinder.RetryInterval = 5
	}

	// Set defaults for individual queries
	for i := range config.Loki.Queries {
		query := &config.Loki.Queries[i]
		if query.MaxEntries == 0 {
			query.MaxEntries = config.Loki.MaxEntriesPerQuery
		}
		if query.Labels == nil {
			query.Labels = make(map[string]string)
		}
		// Note: StartTime and EndTime are calculated dynamically using sampling_interval in worker
	}
}

// validateConfig validates the configuration and returns an error if invalid
func validateConfig(config *Config) error {
	// Validate required Loki fields
	if config.Loki.BaseURL == "" {
		return fmt.Errorf("loki.base_url is required")
	}

	// Validate required InsightFinder fields
	if config.InsightFinder.UserName == "" {
		return fmt.Errorf("insightfinder.username is required")
	}
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder.license_key is required")
	}
	if config.InsightFinder.LogsProjectName == "" {
		return fmt.Errorf("insightfinder.logs_project_name is required")
	}

	// Validate at least one query is configured
	if len(config.Loki.Queries) == 0 {
		return fmt.Errorf("at least one loki query must be configured")
	}

	// Validate individual queries
	for i, query := range config.Loki.Queries {
		if query.Name == "" {
			return fmt.Errorf("query %d: name is required", i)
		}
		if query.Query == "" {
			return fmt.Errorf("query %d (%s): query string is required", i, query.Name)
		}
	}

	// Validate timezone
	if config.Agent.Timezone != "" {
		if _, err := time.LoadLocation(config.Agent.Timezone); err != nil {
			return fmt.Errorf("invalid timezone: %s", config.Agent.Timezone)
		}
	}

	// Validate default instance name (allow empty)
	validFieldNames := map[string]bool{
		"":          true, // Allow empty value
		"container": true,
		"instance":  true,
		"node_name": true,
		"pod":       true,
		"app":       true,
	}
	if !validFieldNames[config.Loki.DefaultInstanceNameField] {
		return fmt.Errorf("invalid default_instance_name_field: %s. Valid options are: (empty), container, instance, node_name, pod, app", config.Loki.DefaultInstanceNameField)
	}

	// Validate query field parameters (allow empty)
	for i, query := range config.Loki.Queries {
		if query.InstanceNameField != "" && !validFieldNames[query.InstanceNameField] {
			return fmt.Errorf("query %d (%s): invalid instance_name_field: %s. Valid options are: (empty), container, instance, node_name, pod, app", i, query.Name, query.InstanceNameField)
		}
		if query.ComponentNameField != "" && !validFieldNames[query.ComponentNameField] {
			return fmt.Errorf("query %d (%s): invalid component_name_field: %s. Valid options are: (empty), container, instance, node_name, pod, app", i, query.Name, query.ComponentNameField)
		}
		if query.ContainerNameField != "" && !validFieldNames[query.ContainerNameField] {
			return fmt.Errorf("query %d (%s): invalid container_name_field: %s. Valid options are: (empty), container, instance, node_name, pod, app", i, query.Name, query.ContainerNameField)
		}
	}

	return nil
}
