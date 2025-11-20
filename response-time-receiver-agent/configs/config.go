package configs

import (
	"fmt"
	"os"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"
)

var AppConfig *Config

// LoadConfig loads the configuration from the specified YAML file
func LoadConfig(configPath string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", configPath)

	// Read the config file
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %v", err)
	}

	// Parse the YAML
	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %v", err)
	}

	// Validate configuration
	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("invalid configuration: %v", err)
	}

	AppConfig = &config
	logrus.Info("Configuration loaded successfully")
	return &config, nil
}

// validateConfig validates the configuration
func validateConfig(config *Config) error {
	// Validate agent config
	if config.Agent.ServerPort <= 0 || config.Agent.ServerPort > 65535 {
		return fmt.Errorf("invalid server_port: must be between 1 and 65535")
	}

	// Validate at least one environment is configured
	if config.Environment.Staging == nil &&
		config.Environment.Production == nil &&
		config.Environment.NBC == nil {
		return fmt.Errorf("at least one environment must be configured")
	}

	// Validate each configured environment
	envs := config.Environment.GetAllEnvironments()
	for envName, envSettings := range envs {
		if err := validateEnvironmentSettings(envName, envSettings); err != nil {
			return err
		}
	}

	return nil
}

// validateEnvironmentSettings validates a single environment's settings
func validateEnvironmentSettings(envName string, settings *EnvironmentSettings) error {
	if settings == nil {
		return fmt.Errorf("environment %s is nil", envName)
	}

	ifConfig := settings.InsightFinder

	// Validate InsightFinder configuration
	if ifConfig.ServerURL == "" {
		return fmt.Errorf("environment %s: server_url is required", envName)
	}
	if ifConfig.Username == "" {
		return fmt.Errorf("environment %s: username is required", envName)
	}
	if ifConfig.LicenseKey == "" {
		return fmt.Errorf("environment %s: license_key is required", envName)
	}
	if ifConfig.MetricsProjectName == "" {
		return fmt.Errorf("environment %s: metrics_project_name is required", envName)
	}

	return nil
}
