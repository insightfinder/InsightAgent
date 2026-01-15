package config

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	NetExperience NetExperienceConfig `yaml:"netexperience"`
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

type NetExperienceConfig struct {
	BaseURL                      string `yaml:"base_url"`
	UserID                       string `yaml:"user_id"`
	Password                     string `yaml:"password"`
	ServiceProviderID            int    `yaml:"service_provider_id"`
	TokenRefreshInterval         int    `yaml:"token_refresh_interval"`
	TokenRetryAttempts           int    `yaml:"token_retry_attempts"`
	TokenRetryDelay              int    `yaml:"token_retry_delay"`
	RateLimitRequests            int    `yaml:"rate_limit_requests"`
	RateLimitPeriod              int    `yaml:"rate_limit_period"`
	MaxConcurrentRequests        int    `yaml:"max_concurrent_requests"`
	EquipmentBatchSize           int    `yaml:"equipment_batch_size"`
	CustomerCacheRefreshHours    int    `yaml:"customer_cache_refresh_hours"`
	EquipmentCacheRefreshHours   int    `yaml:"equipment_cache_refresh_hours"`
	EquipmentIPCacheRefreshHours int    `yaml:"equipment_ip_cache_refresh_hours"`
	MinClientsRSSIThreshold      int    `yaml:"min_clients_rssi_threshold"`
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
	LastCollectionTimestamp       int64 `yaml:"last_collection_timestamp"`
	LastCustomerRefreshTimestamp  int64 `yaml:"last_customer_refresh_timestamp"`
	LastEquipmentRefreshTimestamp int64 `yaml:"last_equipment_refresh_timestamp"`
}
