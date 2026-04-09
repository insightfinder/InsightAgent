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

	// Operation mode:
	//   "continuous"        - (default) poll every sampling_interval indefinitely
	//   "historical"        - download Loki logs to local NDJSON files, then exit
	//   "stream_historical" - stream Loki logs directly to InsightFinder, then exit
	//   "replay"            - read previously downloaded NDJSON files and send to InsightFinder
	Mode      string `yaml:"mode"`
	StartTime string `yaml:"start_time"` // RFC3339 (e.g. "2024-01-01T00:00:00Z") or "2006-01-02"; required for historical/stream_historical
	EndTime   string `yaml:"end_time"`   // Optional; defaults to now if blank

	// historical mode: directory where downloaded NDJSON files are written
	DownloadPath string `yaml:"download_path"`

	// replay mode: file or directory of NDJSON files to replay to InsightFinder
	ReplayPath string `yaml:"replay_path"`

	// stream_historical only: seconds to wait between chunks (0 = no wait)
	StreamChunkInterval int `yaml:"stream_chunk_interval"`
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
	DefaultInstanceNameField string `yaml:"default_instance_name_field"`

	// Query Configuration
	Queries            []QueryConfig `yaml:"queries"`
	MaxEntriesPerQuery int           `yaml:"max_entries_per_query"`
	// Note: Query interval and time ranges are determined by InsightFinder.SamplingInterval
}

// SensitiveDataFilter defines a regex pattern and replacement string for masking sensitive data.
type SensitiveDataFilter struct {
	Regex       string `yaml:"regex"`
	Replacement string `yaml:"replacement"`
}

type QueryConfig struct {
	Name       string            `yaml:"name"`
	Query      string            `yaml:"query"`
	Labels     map[string]string `yaml:"labels"`
	Enabled    bool              `yaml:"enabled"`
	MaxEntries int               `yaml:"max_entries"` // Override default

	// Query field parameters - specify which field to use from log entry
	// Options: container, instance, node_name, pod, app
	InstanceNameField  string `yaml:"instance_name_field"`  // Field name to use for instance name
	ComponentNameField string `yaml:"component_name_field"` // Field name to use for component name
	ContainerNameField string `yaml:"container_name_field"` // Field name to use for container name

	// Sensitive data masking: applied to every log message for this query.
	// Each entry matches the regex and replaces with the given string.
	SensitiveDataFilters []SensitiveDataFilter `yaml:"sensitive_data_filters"`
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
