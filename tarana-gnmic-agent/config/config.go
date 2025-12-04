package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Config represents the entire configuration file
type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	InfluxDB      InfluxDBConfig      `yaml:"influxdb"`
	Gnmic         GnmicConfig         `yaml:"gnmic"`
	Collector     CollectorConfig     `yaml:"collector"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
}

// AgentConfig contains agent-level settings
type AgentConfig struct {
	Name     string `yaml:"name"`
	LogLevel string `yaml:"log_level"`
	LogFile  string `yaml:"log_file"`
}

// InfluxDBConfig contains InfluxDB connection settings
type InfluxDBConfig struct {
	URL    string             `yaml:"url"`
	Token  string             `yaml:"token"`
	Org    string             `yaml:"org"`
	Bucket string             `yaml:"bucket"`
	Docker InfluxDockerConfig `yaml:"docker"`
}

// InfluxDockerConfig contains Docker-specific InfluxDB settings
type InfluxDockerConfig struct {
	Enabled       bool   `yaml:"enabled"`
	Image         string `yaml:"image"`
	ContainerName string `yaml:"container_name"`
	PortMapping   string `yaml:"port_mapping"`
	InitMode      string `yaml:"init_mode"`
	InitUsername  string `yaml:"init_username"`
	InitPassword  string `yaml:"init_password"`
	InitRetention string `yaml:"init_retention"`
}

// GnmicConfig contains gNMIc telemetry settings
type GnmicConfig struct {
	ListenAddress string `yaml:"listen_address"`
	Org           string `yaml:"org"`
	ConfigFile    string `yaml:"config_file"`
	BinaryPath    string `yaml:"binary_path"`
	AutoStart     bool   `yaml:"auto_start"`
}

// CollectorConfig contains metrics collector settings
type CollectorConfig struct {
	TimeRange string `yaml:"time_range"`
}

// MetricConfig represents a single metric configuration
type MetricConfig struct {
	Name  string `yaml:"name"`
	Field string `yaml:"field"`
}

// InsightFinderConfig contains InsightFinder settings (compatible with positron-agent)
type InsightFinderConfig struct {
	Enabled            bool   `yaml:"enabled"`
	ServerURL          string `yaml:"server_url"`
	UserName           string `yaml:"username"` // Changed key to match positron
	LicenseKey         string `yaml:"license_key"`
	MetricsProjectName string `yaml:"metrics_project_name"`
	MetricsSystemName  string `yaml:"metrics_system_name"`
	MetricsProjectType string `yaml:"metrics_project_type"`
	LogsProjectName    string `yaml:"logs_project_name"`
	LogsSystemName     string `yaml:"logs_system_name"`
	LogsProjectType    string `yaml:"logs_project_type"`
	SamplingInterval   int    `yaml:"sampling_interval"` // in seconds
	IsContainer        bool   `yaml:"is_container"`
	CloudType          string `yaml:"cloud_type"`
	InstanceType       string `yaml:"instance_type"`
}

// LoadConfig loads configuration from a YAML file
func LoadConfig(configPath string) (*Config, error) {
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	// Set defaults if not provided
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "info"
	}
	if config.Agent.LogFile == "" {
		config.Agent.LogFile = "logs/agent.log"
	}
	if config.Collector.TimeRange == "" {
		config.Collector.TimeRange = "-5m"
	}
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 60
	}
	if config.InsightFinder.MetricsProjectType == "" {
		config.InsightFinder.MetricsProjectType = "Metric"
	}
	if config.InsightFinder.CloudType == "" {
		config.InsightFinder.CloudType = "PrivateCloud"
	}
	if config.InsightFinder.InstanceType == "" {
		config.InsightFinder.InstanceType = "Tarana"
	}

	return &config, nil
}
