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
	cleanDeviceName := cleanDeviceNamePrefix(ap.DeviceName)

	return &MetricData{
		Timestamp:    time.Now().Unix(),
		InstanceName: cleanDeviceName,
		Data: map[string]interface{}{
			// === CRITICAL FIELDS (Must Monitor) ===
			"Status":                  ap.Status,
			"Connection Status":       ap.ConnectionStatus,
			"Uptime Seconds":          ap.Uptime,
			"Num Clients Total":       ap.NumClients,
			"Num Clients 24G":         ap.NumClients24G,
			"Num Clients 5G":          ap.NumClients5G,
			"Airtime 24G Percent":     ap.Airtime24G,
			"Airtime 5G Percent":      ap.Airtime5G,
			"Connection Failure Rate": ap.ConnectionFailure,
			"Is Health Flagged":       ap.IsOverallHealthStatusFlagged,
			"Is Airtime 24G Flagged":  ap.IsAirtime24GFlagged,
			"Alerts Total":            ap.Alerts,

			// === PERFORMANCE FIELDS (High Priority) ===
			"Total Throughput Bytes": ap.TxRx,
			"Tx Bytes Total":         ap.Tx,
			"Rx Bytes Total":         ap.Rx,
			"Noise 24G Dbm":          ap.Noise24G,
			"Noise 5G Dbm":           ap.Noise5G,
			"Retry 24G Total":        ap.Retry24G,
			"Retry 5G Total":         ap.Retry5G,
			"Latency 24G Microsec":   ap.Latency24G,
			"Latency 5G Microsec":    ap.Latency50G,

			// === CONTEXT FIELDS (Always Include) ===
			// "Device Name":         cleanDeviceName,
			// "Ap Mac":              ap.APMAC,
			// "Ip Address":          ap.IP,
			// "Model":               ap.Model,
			// "Firmware Version":    ap.FirmwareVersion,
			// "Ap Group Name":       ap.APGroupName,
			// "Serial Number":       ap.Serial,
			"Capacity":            ap.Capacity,
			"Last Seen Timestamp": ap.LastSeen,
		},
		Zone: ap.ZoneName,
	}
}
