package configs

import "fmt"

// Config represents the entire application configuration
type Config struct {
	Agent       AgentConfig       `yaml:"agent"`
	Environment EnvironmentConfig `yaml:"environment"`
	Sampler     SamplerConfig     `yaml:"sampler"`
}

// AgentConfig contains general agent settings
type AgentConfig struct {
	ServerPort int    `yaml:"server_port"`
	LogLevel   string `yaml:"log_level"`
}

// SamplerConfig contains periodic sampler settings
type SamplerConfig struct {
	Enabled          bool               `yaml:"enabled"`
	SamplingInterval int                `yaml:"sampling_interval"` // Interval in seconds
	ServerURL        string             `yaml:"server_url"`        // Receiver server URL to send data to
	Metrics          map[string]float64 `yaml:"metrics"`           // Metric keys with their values (typically 0)
}

// EnvironmentConfig contains all environment configurations
type EnvironmentConfig struct {
	SendToAllEnvironments bool                             `yaml:"send_to_all_environments"`
	Environments          map[string][]EnvironmentSettings `yaml:"environments"`
}

// EnvironmentSettings contains settings for a specific environment
type EnvironmentSettings struct {
	InstanceName  string              `yaml:"instancename"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
	MetricListMap map[string]string   `yaml:"metriclistMap"`
}

// InsightFinderConfig contains InsightFinder platform configuration
type InsightFinderConfig struct {
	// InsightFinder Platform Configuration
	ServerURL  string `yaml:"server_url"`
	Username   string `yaml:"username"`
	LicenseKey string `yaml:"license_key"`

	// Metrics Project Configuration
	MetricsProjectName string `yaml:"metrics_project_name"`
	MetricsSystemName  string `yaml:"metrics_system_name"`
	MetricsProjectType string `yaml:"metrics_project_type"`

	// Logs Project Configuration
	LogsProjectName string `yaml:"logs_project_name"`
	LogsSystemName  string `yaml:"logs_system_name"`
	LogsProjectType string `yaml:"logs_project_type"`

	// Common Configuration
	CloudType        string `yaml:"cloud_type"`
	InstanceType     string `yaml:"instance_type"`
	IsContainer      bool   `yaml:"is_container"`
	SamplingInterval int    `yaml:"sampling_interval"`
}

// GetEnvironment returns the settings for a specific environment
// If multiple configurations exist for the same environment name, returns the first one
func (ec *EnvironmentConfig) GetEnvironment(envName string) *EnvironmentSettings {
	if envs, exists := ec.Environments[envName]; exists && len(envs) > 0 {
		return &envs[0]
	}
	return nil
}

// GetEnvironmentInstances returns all instances for a specific environment name
func (ec *EnvironmentConfig) GetEnvironmentInstances(envName string) []EnvironmentSettings {
	if envs, exists := ec.Environments[envName]; exists {
		return envs
	}
	return nil
}

// GetAllEnvironments returns all configured environments as a flat map
// If multiple instances exist for the same environment, they are suffixed with index
func (ec *EnvironmentConfig) GetAllEnvironments() map[string]*EnvironmentSettings {
	envs := make(map[string]*EnvironmentSettings)
	for envName, envList := range ec.Environments {
		for i := range envList {
			key := envName
			if len(envList) > 1 {
				key = fmt.Sprintf("%s-%d", envName, i+1)
			}
			envs[key] = &envList[i]
		}
	}
	return envs
}

// GetAllEnvironmentsList returns all configured environments as a list
func (ec *EnvironmentConfig) GetAllEnvironmentsList() []EnvironmentSettings {
	var allEnvs []EnvironmentSettings
	for _, envList := range ec.Environments {
		allEnvs = append(allEnvs, envList...)
	}
	return allEnvs
}
