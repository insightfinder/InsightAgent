package models

// Tarana device structure from API response
type TaranaDevice struct {
	SerialNumber string `json:"serialNumber"`
	Type         string `json:"type"`
	IP           string `json:"ip"`
	HostName     string `json:"hostName"`
}

// Tarana KPI structure from API response
type TaranaKPI struct {
	KPI               string  `json:"kpi"`
	Value             float64 `json:"value"`
	Time              int64   `json:"time"`
	SampleAggregation string  `json:"sample_aggregation"`
}

// Tarana device metrics structure from API response
type TaranaDeviceMetrics struct {
	DeviceID string      `json:"device_id"`
	KPIs     []TaranaKPI `json:"kpis"`
}

// Tarana alarm detail structure from API response
type TaranaAlarmDetail struct {
	// Essential device identification fields
	DeviceIP           string `json:"deviceIp"`
	DeviceHostName     string `json:"deviceHostName"`
	DeviceSerialNumber string `json:"deviceSerialNumber"`
	RadioType          string `json:"radioType"`

	// Core alarm fields
	ID          string `json:"id"`
	Text        string `json:"text"`
	Status      string `json:"status"`
	Severity    int    `json:"severity"`
	Category    string `json:"category"`
	TimeCleared int64  `json:"time-cleared"`
	TimeCreated int64  `json:"time-created"`
	DisplayID   string `json:"display-id"`

	// Optional fields - commented out to reduce complexity
	// DeviceID           string `json:"device-id"`
	// DeviceIDFull       string `json:"deviceId"`
	// Operator           string `json:"operator"`
	// Band               string `json:"band"`
	// OperatorID         int    `json:"operatorId"`
	// Sector             string `json:"sector"`
	// Market             string `json:"market"`
	// Region             string `json:"region"`
	// SoftwareVersion    string `json:"softwareVersion"`
	// BootReason         string `json:"bootReason"`
	// Access             string `json:"access"`
	// RaiseCount         int    `json:"raise-count"`
	// DisplayResource    string `json:"display-resource"`
	// Cell               string `json:"cell"`
	// MarketID           int    `json:"marketId"`
	// Timestamp          int64  `json:"timestamp"`
	// WriteTime          string `json:"writeTime"`
	// BootTimeSeconds    int64  `json:"bootTimeSeconds"`
	// Retailer           string `json:"retailer"`
	// RetailerID         int    `json:"retailerId"`
	// MSTime             string `json:"msTime"`
	// Site               string `json:"site"`
	// RegionID           int    `json:"regionId"`
	// TimestampNS        int64  `json:"timestampns"`
	// SiteID             int    `json:"siteId"`
	// DeviceTimestamp    int64  `json:"device-timestamp"`
	// RaiseAction        string `json:"raise_action"`
}

// LogData for InsightFinder logs
type LogData struct {
	TimeStamp     int64       `json:"timestamp"`
	Tag           string      `json:"tag"`
	ComponentName string      `json:"componentName"`
	Data          interface{} `json:"data"`
	InstanceName  string      `json:"instanceName"`
	EventId       string      `json:"eventId,omitempty"`
}
