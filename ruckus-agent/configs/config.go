package config

import (
	"fmt"
	"os"

	"gopkg.in/ini.v1"
)

type Config struct {
	Agent         AgentConfig
	Ruckus        RuckusConfig
	InsightFinder InsightFinderConfig
	State         StateConfig
}

type AgentConfig struct {
	CollectionInterval int    `ini:"collection_interval"`
	DataFormat         string `ini:"data_format"`
	Timezone           string `ini:"timezone"`
	LogLevel           string `ini:"log_level"`
	FiltersInclude     string `ini:"filters_include"`
	FiltersExclude     string `ini:"filters_exclude"`
}

type RuckusConfig struct {
	ControllerHost        string `ini:"controller_host"`
	ControllerPort        int    `ini:"controller_port"`
	Username              string `ini:"username"`
	Password              string `ini:"password"`
	APIVersion            string `ini:"api_version"`
	VerifySSL             bool   `ini:"verify_ssl"`
	MaxConcurrentRequests int    `ini:"max_concurrent_requests"`
}

type InsightFinderConfig struct {
	LicenseKey  string `ini:"license_key"`
	ProjectName string `ini:"project_name"`
	ProjectType string `ini:"project_type"`
	UserName    string `ini:"user_name"`
	ServerURL   string `ini:"server_url"`
}

type StateConfig struct {
	LastCollectionTimestamp int64 `ini:"last_collection_timestamp"`
}

func LoadConfig(configPath string) (*Config, error) {
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("config file not found: %s", configPath)
	}

	cfg, err := ini.Load(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load config file: %v", err)
	}

	config := &Config{}

	// Map sections to structs
	if err := cfg.Section("agent").MapTo(&config.Agent); err != nil {
		return nil, fmt.Errorf("failed to load agent config: %v", err)
	}
	if err := cfg.Section("ruckus").MapTo(&config.Ruckus); err != nil {
		return nil, fmt.Errorf("failed to load ruckus config: %v", err)
	}
	if err := cfg.Section("insightfinder").MapTo(&config.InsightFinder); err != nil {
		return nil, fmt.Errorf("failed to load insightfinder config: %v", err)
	}
	if err := cfg.Section("state").MapTo(&config.State); err != nil {
		return nil, fmt.Errorf("failed to load state config: %v", err)
	}

	// Set defaults
	setDefaults(config)

	// Validate required fields
	if err := validateConfig(config); err != nil {
		return nil, err
	}

	return config, nil
}

func setDefaults(config *Config) {
	if config.Agent.CollectionInterval == 0 {
		config.Agent.CollectionInterval = 300
	}
	if config.Agent.DataFormat == "" {
		config.Agent.DataFormat = "JSON"
	}
	if config.Agent.Timezone == "" {
		config.Agent.Timezone = "UTC"
	}
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "INFO"
	}
	if config.Ruckus.ControllerPort == 0 {
		config.Ruckus.ControllerPort = 8443
	}
	if config.Ruckus.APIVersion == "" {
		config.Ruckus.APIVersion = "v11_1"
	}
	if config.InsightFinder.ProjectType == "" {
		config.InsightFinder.ProjectType = "METRIC"
	}
	if config.InsightFinder.ServerURL == "" {
		config.InsightFinder.ServerURL = "https://app.insightfinder.com"
	}
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
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder license_key is required")
	}
	if config.InsightFinder.ProjectName == "" {
		return fmt.Errorf("insightfinder project_name is required")
	}
	return nil
}
