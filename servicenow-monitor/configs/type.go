package config

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	ServiceNow    ServiceNowConfig    `yaml:"servicenow"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
}

type AgentConfig struct {
	LogLevel string `yaml:"log_level"`
}

// ServiceNowConfig holds defaults shared by every instance plus the list of
// instances to monitor. Add a new entry under `instances` to monitor another
// ServiceNow instance; set `enabled: false` to skip one without deleting it.
type ServiceNowConfig struct {
	TimeoutSec       int    `yaml:"timeout_sec"`
	VerifySSL        bool   `yaml:"verify_ssl"`
	ShortDescription string `yaml:"short_description"`
	DeleteAfterCheck bool   `yaml:"delete_after_check"`
	// Create and read are each attempted up to MaxRetries times, waiting
	// RetryIntervalSec between attempts, before the check is marked failed.
	MaxRetries       int                  `yaml:"max_retries"`
	RetryIntervalSec int                  `yaml:"retry_interval_sec"`
	Instances        []ServiceNowInstance `yaml:"instances"`
}

type ServiceNowInstance struct {
	// Name is used as the InsightFinder instance name. Defaults to the
	// subdomain of the URL (e.g. dev428447 for https://dev428447.service-now.com).
	Name     string `yaml:"name"`
	URL      string `yaml:"url"`
	Username string `yaml:"username"`
	Password string `yaml:"password"`
	Enabled  bool   `yaml:"enabled"`
}

type InsightFinderConfig struct {
	ServerURL  string `yaml:"server_url"`
	UserName   string `yaml:"username"`
	LicenseKey string `yaml:"license_key"`

	ProjectName string `yaml:"project_name"`
	SystemName  string `yaml:"system_name"`

	SamplingInterval int    `yaml:"sampling_interval"` // in seconds
	CloudType        string `yaml:"cloud_type"`        // OnPremise, AWS, Azure, etc.
	InstanceType     string `yaml:"instance_type"`     // OnPremise, EC2, etc.
	ComponentName    string `yaml:"component_name"`
}
