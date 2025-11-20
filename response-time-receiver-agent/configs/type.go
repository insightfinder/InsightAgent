package configs

// Config represents the entire application configuration
type Config struct {
	Agent       AgentConfig       `yaml:"agent"`
	Environment EnvironmentConfig `yaml:"environment"`
}

// AgentConfig contains general agent settings
type AgentConfig struct {
	ServerPort int    `yaml:"server_port"`
	LogLevel   string `yaml:"log_level"`
}

// EnvironmentConfig contains all environment configurations
type EnvironmentConfig struct {
	SendToAllEnvironments bool                 `yaml:"send_to_all_environments"`
	Staging               *EnvironmentSettings `yaml:"staging,omitempty"`
	Production            *EnvironmentSettings `yaml:"production,omitempty"`
	NBC                   *EnvironmentSettings `yaml:"nbc,omitempty"`
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
func (ec *EnvironmentConfig) GetEnvironment(envName string) *EnvironmentSettings {
	switch envName {
	case "staging":
		return ec.Staging
	case "production":
		return ec.Production
	case "nbc":
		return ec.NBC
	default:
		return nil
	}
}

// GetAllEnvironments returns all configured environments
func (ec *EnvironmentConfig) GetAllEnvironments() map[string]*EnvironmentSettings {
	envs := make(map[string]*EnvironmentSettings)
	if ec.Staging != nil {
		envs["staging"] = ec.Staging
	}
	if ec.Production != nil {
		envs["production"] = ec.Production
	}
	if ec.NBC != nil {
		envs["nbc"] = ec.NBC
	}
	return envs
}
