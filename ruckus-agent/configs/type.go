package config

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Ruckus        RuckusConfig        `yaml:"ruckus"`
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

type RuckusConfig struct {
	ControllerHost        string `yaml:"controller_host"`
	ControllerPort        int    `yaml:"controller_port"`
	Username              string `yaml:"username"`
	Password              string `yaml:"password"`
	APIVersion            string `yaml:"api_version"`
	VerifySSL             bool   `yaml:"verify_ssl"`
	MaxConcurrentRequests int    `yaml:"max_concurrent_requests"`
	SendComponentNameAsAP bool   `yaml:"send_component_name_as_AP"`
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

type StateConfig struct {
	LastCollectionTimestamp int64 `yaml:"last_collection_timestamp"`
}
