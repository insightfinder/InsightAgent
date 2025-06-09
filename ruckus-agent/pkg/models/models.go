package models

import "time"

// API Response structures
type APListResponse struct {
	TotalCount int      `json:"totalCount"`
	HasMore    bool     `json:"hasMore"`
	FirstIndex int      `json:"firstIndex"`
	List       []APInfo `json:"list"`
}

type APInfo struct {
	MAC       string `json:"mac"`
	ZoneID    string `json:"zoneId"`
	APGroupID string `json:"apGroupId"`
	Serial    string `json:"serial"`
	Name      string `json:"name"`
}

type APQueryRequest struct {
	ExtraFilters []Filter `json:"extraFilters"`
}

type Filter struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}

type APDetailResponse struct {
	TotalCount int        `json:"totalCount"`
	HasMore    bool       `json:"hasMore"`
	FirstIndex int        `json:"firstIndex"`
	List       []APDetail `json:"list"`
}

type APDetail struct {
	// Context Fields (Always Include)
	DeviceName      string `json:"deviceName"`
	APMAC           string `json:"apMac"`
	IP              string `json:"ip"`
	ZoneName        string `json:"zoneName"`
	Model           string `json:"model"`
	FirmwareVersion string `json:"firmwareVersion"`
	LastSeen        int64  `json:"lastSeen"`

	// Critical Fields (Must Monitor)
	Status                       string  `json:"status"`
	ConnectionStatus             string  `json:"connectionStatus"`
	Uptime                       int64   `json:"uptime"`
	Alerts                       int     `json:"alerts"`
	NumClients                   int     `json:"numClients"`
	NumClients24G                int     `json:"numClients24G"`
	NumClients5G                 int     `json:"numClients5G"`
	Airtime24G                   float64 `json:"airtime24G"`
	Airtime5G                    float64 `json:"airtime5G"`
	ConnectionFailure            float64 `json:"connectionFailure"`
	IsOverallHealthStatusFlagged bool    `json:"isOverallHealthStatusFlagged"`
	IsAirtime24GFlagged          bool    `json:"isAirtimeUtilization24GFlagged"`

	// Performance Fields (High Priority)
	TxRx       int64 `json:"txRx"`
	Tx         int64 `json:"tx"`
	Rx         int64 `json:"rx"`
	Noise24G   int   `json:"noise24G"`
	Noise5G    int   `json:"noise5G"`
	Retry24G   int64 `json:"retry24G"`
	Retry5G    int64 `json:"retry5G"`
	Latency24G int64 `json:"latency24G"`
	Latency50G int64 `json:"latency50G"`

	// Additional useful fields
	Capacity    int    `json:"capacity"`
	Serial      string `json:"serial"`
	APGroupName string `json:"apGroupName"`
}

// InsightFinder data structure
type MetricData struct {
	Timestamp    int64                  `json:"timestamp"`
	InstanceName string                 `json:"instanceName"`
	Data         map[string]interface{} `json:"data"`
	Zone         string                 `json:"zone,omitempty"`
}

// Convert AP detail to metric data
func (ap *APDetail) ToMetricData() *MetricData {
	capacityUtil := 0.0
	if ap.Capacity > 0 {
		capacityUtil = float64(ap.NumClients) / float64(ap.Capacity) * 100
	}

	return &MetricData{
		Timestamp:    time.Now().Unix(),
		InstanceName: ap.DeviceName,
		Data: map[string]interface{}{
			// === CRITICAL FIELDS (Must Monitor) ===
			"status":                  ap.Status,
			"connection_status":       ap.ConnectionStatus,
			"uptime_seconds":          ap.Uptime,
			"num_clients_total":       ap.NumClients,
			"num_clients_24g":         ap.NumClients24G,
			"num_clients_5g":          ap.NumClients5G,
			"airtime_24g_percent":     ap.Airtime24G,
			"airtime_5g_percent":      ap.Airtime5G,
			"connection_failure_rate": ap.ConnectionFailure,
			"is_health_flagged":       ap.IsOverallHealthStatusFlagged,
			"is_airtime_24g_flagged":  ap.IsAirtime24GFlagged,
			"alerts_total":            ap.Alerts,

			// === PERFORMANCE FIELDS (High Priority) ===
			"total_throughput_bytes": ap.TxRx,
			"tx_bytes_total":         ap.Tx,
			"rx_bytes_total":         ap.Rx,
			"noise_24g_dbm":          ap.Noise24G,
			"noise_5g_dbm":           ap.Noise5G,
			"retry_24g_total":        ap.Retry24G,
			"retry_5g_total":         ap.Retry5G,
			"latency_24g_microsec":   ap.Latency24G,
			"latency_5g_microsec":    ap.Latency50G,

			// === CONTEXT FIELDS (Always Include) ===
			"device_name":         ap.DeviceName,
			"ap_mac":              ap.APMAC,
			"ip_address":          ap.IP,
			"model":               ap.Model,
			"firmware_version":    ap.FirmwareVersion,
			"last_seen_timestamp": ap.LastSeen,
			"ap_group_name":       ap.APGroupName,
			"serial_number":       ap.Serial,
			// "zone_name":           ap.ZoneName,

			// === DERIVED METRICS ===
			"capacity_utilization_pct": capacityUtil,
		},
		Zone: ap.ZoneName,
	}
}
