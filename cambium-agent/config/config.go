package config

import (
	"fmt"
	"os"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"
)

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Cambium       CambiumConfig       `yaml:"cambium"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
	MetricFilter  MetricFilterConfig  `yaml:"metric_filter"`
	Threshold     ThresholdConfig     `yaml:"threshold"`
}

type AgentConfig struct {
	DataFormat     string `yaml:"data_format"`
	Timezone       string `yaml:"timezone"`
	LogLevel       string `yaml:"log_level"`
	FiltersInclude string `yaml:"filters_include"`
	FiltersExclude string `yaml:"filters_exclude"`
}

type CambiumConfig struct {
	Email              string `yaml:"email"`
	Password           string `yaml:"password"`
	BaseURL            string `yaml:"base_url"`
	LoginURL           string `yaml:"login_url"`
	MaxRetries         int    `yaml:"max_retries"`
	WorkerCount        int    `yaml:"worker_count"`
	CollectionInterval int    `yaml:"collection_interval_seconds"`
}

type InsightFinderConfig struct {
	ServerURL        string `yaml:"server_url"`
	UserName         string `yaml:"username"`
	LicenseKey       string `yaml:"license_key"`
	ProjectName      string `yaml:"project_name"`
	SystemName       string `yaml:"system_name"`
	SamplingInterval int    `yaml:"sampling_interval"` // in seconds
	CloudType        string `yaml:"cloud_type"`        // OnPremise, AWS, Azure, etc.
	InstanceType     string `yaml:"instance_type"`     // OnPremise, EC2, etc.
	ProjectType      string `yaml:"project_type"`      // Metric, Log, etc.
	IsContainer      bool   `yaml:"is_container"`      // Container deployment flag
}

type MetricFilterConfig struct {
	// System metrics
	AvailableMemory bool `yaml:"available_memory"`
	CPUUtilization  bool `yaml:"cpu_utilization"`

	// Radio metrics
	NumClients5G         bool `yaml:"num_clients_5g"`
	ChannelUtilization5G bool `yaml:"channel_utilization_5g"`
	NumClients6G         bool `yaml:"num_clients_6g"`
	ChannelUtilization6G bool `yaml:"channel_utilization_6g"`

	// Client-derived metrics
	RSSIAvg            bool `yaml:"rssi_avg"`
	SNRAvg             bool `yaml:"snr_avg"`
	ClientsRSSIBelow74 bool `yaml:"clients_rssi_below_74"`
	ClientsRSSIBelow78 bool `yaml:"clients_rssi_below_78"`
	ClientsRSSIBelow80 bool `yaml:"clients_rssi_below_80"`
	ClientsSNRBelow15  bool `yaml:"clients_snr_below_15"`
	ClientsSNRBelow18  bool `yaml:"clients_snr_below_18"`
	ClientsSNRBelow20  bool `yaml:"clients_snr_below_20"`
}

type ThresholdConfig struct {
	MinClientsRSSIThreshold int `yaml:"min_clients_rssi_threshold"`
	MinClientsSNRThreshold  int `yaml:"min_clients_snr_threshold"`
}

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

func setDefaults(config *Config) {
	// Cambium defaults
	if config.Cambium.MaxRetries == 0 {
		config.Cambium.MaxRetries = 3
	}
	if config.Cambium.WorkerCount == 0 {
		config.Cambium.WorkerCount = 10
	}
	if config.Cambium.CollectionInterval == 0 {
		config.Cambium.CollectionInterval = 60
	}
	if config.Cambium.LoginURL == "" {
		config.Cambium.LoginURL = "https://cloud.cambiumnetworks.com/#/"
	}

	// Agent defaults
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "INFO"
	}
	if config.Agent.DataFormat == "" {
		config.Agent.DataFormat = "JSON"
	}
	if config.Agent.Timezone == "" {
		config.Agent.Timezone = "UTC"
	}

	// InsightFinder defaults
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 60 // 1 minute default
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

	// MetricFilter defaults are handled by YAML parsing and Go's zero values
	// No need to override them here since false is the desired default

	// Threshold defaults
	if config.Threshold.MinClientsRSSIThreshold == 0 {
		config.Threshold.MinClientsRSSIThreshold = 10 // Default to 10 clients
	}
	if config.Threshold.MinClientsSNRThreshold == 0 {
		config.Threshold.MinClientsSNRThreshold = 10 // Default to 10 clients
	}

	logrus.Debug("Default values applied to configuration")
}

func validateConfig(config *Config) error {
	// Validate Cambium config
	if config.Cambium.Email == "" {
		return fmt.Errorf("cambium email is required")
	}
	if config.Cambium.Password == "" {
		return fmt.Errorf("cambium password is required")
	}
	if config.Cambium.BaseURL == "" {
		return fmt.Errorf("cambium base_url is required")
	}

	// Validate InsightFinder config
	if config.InsightFinder.ServerURL == "" {
		return fmt.Errorf("insightfinder server_url is required")
	}
	if config.InsightFinder.UserName == "" {
		return fmt.Errorf("insightfinder username is required")
	}
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder license_key is required")
	}
	if config.InsightFinder.ProjectName == "" {
		return fmt.Errorf("insightfinder project_name is required")
	}

	return nil
}
