package config

import (
	"fmt"
	"os"

	"github.com/sirupsen/logrus"
	"gopkg.in/ini.v1"
)

func LoadConfig(configPath string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", configPath)

	// Check if file exists
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("configuration file does not exist: %s", configPath)
	}

	// Load INI file
	cfg, err := ini.Load(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load INI file: %v", err)
	}

	var config Config

	// Load Ruckus section
	if err := cfg.Section("ruckus").MapTo(&config.Ruckus); err != nil {
		return nil, fmt.Errorf("failed to map ruckus section: %v", err)
	}

	// Load InsightFinder section
	if err := cfg.Section("insightfinder").MapTo(&config.InsightFinder); err != nil {
		return nil, fmt.Errorf("failed to map insightfinder section: %v", err)
	}

	// Load Agent section
	if err := cfg.Section("agent").MapTo(&config.Agent); err != nil {
		return nil, fmt.Errorf("failed to map agent section: %v", err)
	}

	// Validate and set defaults
	setDefaults(&config)
	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %v", err)
	}

	logrus.Info("Configuration loaded successfully")
	return &config, nil
}

func setDefaults(config *Config) {
	// Ruckus defaults
	if config.Ruckus.ControllerPort == 0 {
		config.Ruckus.ControllerPort = 8443
	}
	if config.Ruckus.APIVersion == "" {
		config.Ruckus.APIVersion = "v10_0"
	}
	if config.Ruckus.MaxConcurrentRequests == 0 {
		config.Ruckus.MaxConcurrentRequests = 20
	}

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
	if config.InsightFinder.ProjectType == "" {
		config.InsightFinder.ProjectType = "Metric"
	}
	if config.InsightFinder.SystemName == "" {
		config.InsightFinder.SystemName = config.InsightFinder.ProjectName
	}

	logrus.Debug("Default values applied to configuration")
}

func validateConfig(config *Config) error {
	if config.Ruckus.ControllerHost == "" {
		return fmt.Errorf("ruckus controller_host is required")
	}
	if config.Ruckus.Username == "" {
		return fmt.Errorf("ruckus username is required")
	}
	if config.Ruckus.Password == "" {
		return fmt.Errorf("ruckus password is required")
	}

	if config.InsightFinder.ServerURL == "" {
		return fmt.Errorf("insightfinder server_url is required")
	}
	if config.InsightFinder.UserName == "" {
		return fmt.Errorf("insightfinder username is required")
	}
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder license_key is required")
	}

	return nil
}
