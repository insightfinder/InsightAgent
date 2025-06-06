package config

type Config struct {
	Agent         AgentConfig
	Ruckus        RuckusConfig
	InsightFinder InsightFinderConfig
	State         StateConfig
}

type AgentConfig struct {
	DataFormat     string `ini:"data_format"`
	Timezone       string `ini:"timezone"`
	LogLevel       string `ini:"log_level"`
	FiltersInclude string `ini:"filters_include"`
	FiltersExclude string `ini:"filters_exclude"`
}

type RuckusConfig struct {
	ControllerHost        string `ini:"controller_host"`
	ControllerPort        int    `ini:"controller_port"`
	Username              string `ini:"username"`
	Password              string `ini:"password"`
	APIVersion            string `ini:"api_version"`
	VerifySSL             bool   `ini:"verify_ssl"`
	MaxConcurrentRequests int    `ini:"max_concurrent_requests"`
}

type InsightFinderConfig struct {
	ServerURL        string `ini:"server_url"`
	UserName         string `ini:"username"`
	LicenseKey       string `ini:"license_key"`
	ProjectName      string `ini:"project_name"`
	SystemName       string `ini:"system_name"`
	SamplingInterval int    `ini:"sampling_interval"` // in seconds
	CloudType        string `ini:"cloud_type"`        // OnPremise, AWS, Azure, etc.
	InstanceType     string `ini:"instance_type"`     // OnPremise, EC2, etc.
	ProjectType      string `ini:"project_type"`      // Metric, Log, etc.
	IsContainer      bool   `ini:"is_container"`      // Container deployment flag
}

type StateConfig struct {
	LastCollectionTimestamp int64 `ini:"last_collection_timestamp"`
}
