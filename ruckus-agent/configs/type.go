package config

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Ruckus        RuckusConfig        `yaml:"ruckus"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
	State         StateConfig         `yaml:"state"`
	MetricFilter  MetricFilterConfig  `yaml:"metric_filter"`
	Threshold     ThresholdConfig     `yaml:"threshold"`
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

type ThresholdConfig struct {
	MinClientsRSSIThreshold int `yaml:"min_clients_rssi_threshold"`
	MinClientsSNRThreshold  int `yaml:"min_clients_snr_threshold"`
}

type MetricFilterConfig struct {
	// Client count metrics
	NumClientsTotal bool `yaml:"num_clients_total"`
	NumClients24G   bool `yaml:"num_clients_24g"`
	NumClients5G    bool `yaml:"num_clients_5g"`
	NumClients6G    bool `yaml:"num_clients_6g"`

	// Airtime metrics
	Airtime24G bool `yaml:"airtime_24g"`
	Airtime5G  bool `yaml:"airtime_5g"`
	Airtime6G  bool `yaml:"airtime_6g"`

	// Airtime metrics with client threshold
	Airtime24GClientsOver35 bool `yaml:"airtime_24g_clients_over_35"`
	Airtime5GClientsOver35  bool `yaml:"airtime_5g_clients_over_35"`
	Airtime6GClientsOver35  bool `yaml:"airtime_6g_clients_over_35"`

	// Client-derived metrics
	RSSIAvg            bool `yaml:"rssi_avg"`
	SNRAvg             bool `yaml:"snr_avg"`
	ClientsRSSIBelow74 bool `yaml:"clients_rssi_below_74"`
	ClientsRSSIBelow78 bool `yaml:"clients_rssi_below_78"`
	ClientsRSSIBelow80 bool `yaml:"clients_rssi_below_80"`
	ClientsSNRBelow15  bool `yaml:"clients_snr_below_15"`
	ClientsSNRBelow18  bool `yaml:"clients_snr_below_18"`
	ClientsSNRBelow20  bool `yaml:"clients_snr_below_20"`

	// Ethernet metrics
	EthernetStatusMbps bool `yaml:"ethernet_status_mbps"`
}

// Implement the MetricFilter interface
func (m *MetricFilterConfig) IsNumClientsTotal() bool         { return m.NumClientsTotal }
func (m *MetricFilterConfig) IsNumClients24G() bool           { return m.NumClients24G }
func (m *MetricFilterConfig) IsNumClients5G() bool            { return m.NumClients5G }
func (m *MetricFilterConfig) IsNumClients6G() bool            { return m.NumClients6G }
func (m *MetricFilterConfig) IsAirtime24G() bool              { return m.Airtime24G }
func (m *MetricFilterConfig) IsAirtime5G() bool               { return m.Airtime5G }
func (m *MetricFilterConfig) IsAirtime6G() bool               { return m.Airtime6G }
func (m *MetricFilterConfig) IsAirtime24GClientsOver35() bool { return m.Airtime24GClientsOver35 }
func (m *MetricFilterConfig) IsAirtime5GClientsOver35() bool  { return m.Airtime5GClientsOver35 }
func (m *MetricFilterConfig) IsAirtime6GClientsOver35() bool  { return m.Airtime6GClientsOver35 }
func (m *MetricFilterConfig) IsRSSIAvg() bool                 { return m.RSSIAvg }
func (m *MetricFilterConfig) IsSNRAvg() bool                  { return m.SNRAvg }
func (m *MetricFilterConfig) IsClientsRSSIBelow74() bool      { return m.ClientsRSSIBelow74 }
func (m *MetricFilterConfig) IsClientsRSSIBelow78() bool      { return m.ClientsRSSIBelow78 }
func (m *MetricFilterConfig) IsClientsRSSIBelow80() bool      { return m.ClientsRSSIBelow80 }
func (m *MetricFilterConfig) IsClientsSNRBelow15() bool       { return m.ClientsSNRBelow15 }
func (m *MetricFilterConfig) IsClientsSNRBelow18() bool       { return m.ClientsSNRBelow18 }
func (m *MetricFilterConfig) IsClientsSNRBelow20() bool       { return m.ClientsSNRBelow20 }
func (m *MetricFilterConfig) IsEthernetStatusMbps() bool      { return m.EthernetStatusMbps }
