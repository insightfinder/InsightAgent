package configs

// Config is the top-level configuration structure.
type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Splunk        SplunkConfig        `yaml:"splunk"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
}

// AgentConfig controls agent-level behaviour.
type AgentConfig struct {
	LogLevel string `yaml:"log_level"` // DEBUG | INFO | WARN | ERROR
	Mode     string `yaml:"mode"`      // "continuous" (only mode for now)
}

// SplunkConfig holds connection and query settings for Splunk.
type SplunkConfig struct {
	// Connection
	ServerURL string `yaml:"server_url"` // e.g. https://localhost:8089
	Username  string `yaml:"username"`   // Enterprise basic-auth
	Password  string `yaml:"password"`   // Enterprise basic-auth
	Token     string `yaml:"token"`      // Splunk Cloud token (overrides user/pass)
	VerifySSL bool   `yaml:"verify_ssl"`

	// Query defaults
	MaxRetries   int `yaml:"max_retries"`
	QueryTimeout int `yaml:"query_timeout"` // seconds to wait for a Splunk job
	MaxResults   int `yaml:"max_results"`   // default max events per query run

	// Concurrency
	// ConcurrentQueries runs all enabled queries in parallel when true.
	// By default queries run sequentially (false).
	ConcurrentQueries bool `yaml:"concurrent_queries"`
	// MaxConcurrent limits the number of queries running at the same time.
	// 0 means no limit (all enabled queries at once). Only used when
	// ConcurrentQueries is true.
	MaxConcurrent int `yaml:"max_concurrent"`

	// Queries to run
	Queries []QueryConfig `yaml:"queries"`
}

// QueryConfig defines a single Splunk SPL query.
type QueryConfig struct {
	Name       string `yaml:"name"`
	Query      string `yaml:"query"`   // SPL without time modifiers — agent adds earliest/latest
	Enabled    bool   `yaml:"enabled"`
	MaxResults int    `yaml:"max_results"` // 0 → use SplunkConfig.MaxResults

	// Per-query field mapping overrides (empty = fall back to global insightfinder settings).
	// TagField is the name of the Splunk field whose value becomes the IF instance/tag name.
	// TagValue, when non-empty, sets a static tag for every event in this query (ignores TagField).
	TagField   string `yaml:"instance_field"`
	TagValue   string `yaml:"instance_value"`
	// ComponentField is the name of the Splunk field whose value becomes the IF componentName.
	// ComponentValue, when non-empty, sets a static component for every event (ignores ComponentField).
	ComponentField  string `yaml:"component_field"`
	ComponentValue  string `yaml:"component_value"`
}

// InsightFinderConfig holds the IF project and HTTP settings.
type InsightFinderConfig struct {
	ServerURL  string `yaml:"server_url"`
	UserName   string `yaml:"username"`
	LicenseKey string `yaml:"license_key"`

	LogsProjectName string `yaml:"logs_project_name"`
	LogsSystemName  string `yaml:"logs_system_name"`
	LogsProjectType string `yaml:"logs_project_type"` // always "LOG"

	SamplingInterval int    `yaml:"sampling_interval"` // seconds between polls
	CloudType        string `yaml:"cloud_type"`        // OnPremise | AWS | Azure …
	InstanceType     string `yaml:"instance_type"`     // OnPremise | EC2 …
	IsContainer      bool   `yaml:"is_container"`

	HTTPProxy  string `yaml:"http_proxy"`
	HTTPSProxy string `yaml:"https_proxy"`

	ChunkSize     int `yaml:"chunk_size"`      // bytes — split payload above this
	MaxPacketSize int `yaml:"max_packet_size"` // bytes — hard max per HTTP call
	RetryTimes    int `yaml:"retry_times"`
	RetryInterval int `yaml:"retry_interval"` // seconds between retries

	// Global field mapping — used when a query does not define its own overrides.
	// TagField is the Splunk field name whose value becomes the IF instance/tag.
	// Default: "host"
	TagField string `yaml:"instance_field"`
	// TagValue, when non-empty, sets a static instance for every event (overrides TagField).
	TagValue string `yaml:"instance_value"`
	// ComponentField is the Splunk field name whose value becomes the IF componentName.
	// Default: "sourcetype"
	ComponentField string `yaml:"component_field"`
	// ComponentValue, when non-empty, sets a static component for every event.
	ComponentValue string `yaml:"component_value"`
}
