package config

import (
	"fmt"
	"os"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v2"
)

// Config represents the overall configuration structure
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
		config.Agent.LogLevel = "info"
	}

	// InsightFinder defaults - sampling_interval is now the main collection interval
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 300 // 5 minutes default
	}
	if config.InsightFinder.CloudType == "" {
		config.InsightFinder.CloudType = "OnPremise"
	}
	if config.InsightFinder.InstanceType == "" {
		config.InsightFinder.InstanceType = "OnPremise"
	}
	// Set defaults for metrics project if not provided
	if config.InsightFinder.MetricsProjectType == "" {
		config.InsightFinder.MetricsProjectType = "Metric"
	}
	if config.InsightFinder.MetricsSystemName == "" {
		config.InsightFinder.MetricsSystemName = config.InsightFinder.MetricsProjectName
	}
	// Set defaults for logs project if not provided
	if config.InsightFinder.LogsProjectType == "" {
		config.InsightFinder.LogsProjectType = "Log"
	}
	if config.InsightFinder.LogsSystemName == "" {
		config.InsightFinder.LogsSystemName = config.InsightFinder.LogsProjectName
	}

	logrus.Debug("Default values applied to configuration")
}

// validateConfig validates the configuration
func validateConfig(config *Config) error {
	// Validate Tarana configuration
	if config.Tarana.BaseURL == "" {
		return fmt.Errorf("tarana.base_url is required")
	}
	if config.Tarana.Username == "" {
		return fmt.Errorf("tarana.username is required")
	}
	if config.Tarana.Password == "" {
		return fmt.Errorf("tarana.password is required")
	}
	if len(config.Tarana.RegionIDs) == 0 {
		return fmt.Errorf("tarana.region_ids is required")
	}
	if len(config.Tarana.KPIs) == 0 {
		return fmt.Errorf("tarana.kpis is required")
	}

	// Validate InsightFinder configuration
	if config.InsightFinder.ServerURL == "" {
		return fmt.Errorf("insightfinder.server_url is required")
	}
	if config.InsightFinder.UserName == "" {
		return fmt.Errorf("insightfinder.username is required")
	}
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder.license_key is required")
	}
	if config.InsightFinder.MetricsProjectName == "" {
		return fmt.Errorf("insightfinder.metrics_project_name is required")
	}
	if config.InsightFinder.LogsProjectName == "" {
		return fmt.Errorf("insightfinder.logs_project_name is required")
	}

	// Set defaults
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 60 // Default to 60 seconds
	}
	if config.Tarana.MaxConcurrentRequests == 0 {
		config.Tarana.MaxConcurrentRequests = 10 // Default to 10 concurrent requests
	}
	if config.Tarana.TokenRefreshThreshold == 0 {
		config.Tarana.TokenRefreshThreshold = 300 // Default to 5 minutes before expiry
	}

	return nil
}
