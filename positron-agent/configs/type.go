package config

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Positron      PositronConfig      `yaml:"positron"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
	State         StateConfig         `yaml:"state"`
}

type AgentConfig struct {
	DataFormat     string `yaml:"data_format"`
	Timezone       string `yaml:"timezone"`
	LogLevel       string `yaml:"log_level"`
	FiltersInclude string `yaml:"filters_include"`
	FiltersExclude string `yaml:"filters_exclude"`
}

type PositronConfig struct {
	ControllerHost        string `yaml:"controller_host"`
	ControllerPort        int    `yaml:"controller_port"`
	Username              string `yaml:"username"`
	Password              string `yaml:"password"`
	VerifySSL             bool   `yaml:"verify_ssl"`
	MaxConcurrentRequests int    `yaml:"max_concurrent_requests"`
}

type InsightFinderConfig struct {
	ServerURL  string `yaml:"server_url"`
	UserName   string `yaml:"username"`
	LicenseKey string `yaml:"license_key"`

	// Metrics Project
	MetricsProjectName string `yaml:"metrics_project_name"`
	MetricsSystemName  string `yaml:"metrics_system_name"`
	MetricsProjectType string `yaml:"metrics_project_type"`

	// Logs Project
	LogsProjectName string `yaml:"logs_project_name"`
	LogsSystemName  string `yaml:"logs_system_name"`
	LogsProjectType string `yaml:"logs_project_type"`

	// Common settings
	SamplingInterval int    `yaml:"sampling_interval"` // in seconds
	CloudType        string `yaml:"cloud_type"`        // OnPremise, AWS, Azure, etc.
	InstanceType     string `yaml:"instance_type"`     // OnPremise, EC2, etc.
	IsContainer      bool   `yaml:"is_container"`      // Container deployment flag
}

type StateConfig struct {
	LastCollectionTimestamp int64 `yaml:"last_collection_timestamp"`
}
