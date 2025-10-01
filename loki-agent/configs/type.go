package config

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Loki          LokiConfig          `yaml:"loki"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
}

type AgentConfig struct {
	DataFormat     string `yaml:"data_format"`
	Timezone       string `yaml:"timezone"`
	LogLevel       string `yaml:"log_level"`
	FiltersInclude string `yaml:"filters_include"`
	FiltersExclude string `yaml:"filters_exclude"`
}

type LokiConfig struct {
	BaseURL               string `yaml:"base_url"`
	Username              string `yaml:"username"`
	Password              string `yaml:"password"`
	VerifySSL             bool   `yaml:"verify_ssl"`
	MaxConcurrentRequests int    `yaml:"max_concurrent_requests"`
	MaxRetries            int    `yaml:"max_retries"`
	QueryTimeout          int    `yaml:"query_timeout"` // in seconds

	// Default instance name field - determines what field to use as default instance name/tag
	// Options: container, instance, node_name, pod, app
	DefaultInstanceName string `yaml:"default_instance_name"`

	// Query Configuration
	Queries            []QueryConfig `yaml:"queries"`
	MaxEntriesPerQuery int           `yaml:"max_entries_per_query"`
	// Note: Query interval and time ranges are determined by InsightFinder.SamplingInterval
}

type QueryConfig struct {
	Name       string            `yaml:"name"`
	Query      string            `yaml:"query"`
	Labels     map[string]string `yaml:"labels"`
	Enabled    bool              `yaml:"enabled"`
	MaxEntries int               `yaml:"max_entries"` // Override default

	// Query field parameters - specify which field to use from log entry
	// Options: container, instance, node_name, pod, app
	InstanceName  string `yaml:"instance_name"`  // Field name to use for instance name
	ComponentName string `yaml:"component_name"` // Field name to use for component name
	ContainerName string `yaml:"container_name"` // Field name to use for container name
}

type InsightFinderConfig struct {
	ServerURL  string `yaml:"server_url"`
	UserName   string `yaml:"username"`
	LicenseKey string `yaml:"license_key"`

	// Logs Project (Loki primarily deals with logs)
	LogsProjectName  string `yaml:"logs_project_name"`
	LogsSystemName   string `yaml:"logs_system_name"`
	LogsProjectType  string `yaml:"logs_project_type"` // Common settings
	SamplingInterval int    `yaml:"sampling_interval"` // in seconds
	CloudType        string `yaml:"cloud_type"`        // OnPremise, AWS, Azure, etc.
	InstanceType     string `yaml:"instance_type"`     // OnPremise, EC2, etc.
	IsContainer      bool   `yaml:"is_container"`
	HTTPProxy        string `yaml:"http_proxy"`
	HTTPSProxy       string `yaml:"https_proxy"`

	// Advanced settings
	ChunkSize     int `yaml:"chunk_size"`      // in bytes
	MaxPacketSize int `yaml:"max_packet_size"` // in bytes
	RetryTimes    int `yaml:"retry_times"`
	RetryInterval int `yaml:"retry_interval"` // in seconds
}
