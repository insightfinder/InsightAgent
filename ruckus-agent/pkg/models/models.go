package models

import "time"

// MetricFilter interface to support filtering
type MetricFilter interface {
	IsNumClientsTotal() bool
	IsNumClients24G() bool
	IsNumClients5G() bool
	IsNumClients6G() bool
	IsAirtime24G() bool
	IsAirtime5G() bool
	IsAirtime6G() bool
	IsAirtime24GClientsOver35() bool
	IsAirtime5GClientsOver35() bool
	IsAirtime6GClientsOver35() bool
	IsRSSIAvg() bool
	IsSNRAvg() bool
	IsClientsRSSIBelow74() bool
	IsClientsRSSIBelow78() bool
	IsClientsRSSIBelow80() bool
	IsClientsSNRBelow15() bool
	IsClientsSNRBelow18() bool
	IsClientsSNRBelow20() bool
	IsEthernetStatusMbps() bool
}

// API Response structures
type APListResponse struct {
	TotalCount int      `json:"totalCount"`
	HasMore    bool     `json:"hasMore"`
	FirstIndex int      `json:"firstIndex"`
	List       []APInfo `json:"list"`
}

// Client API Response structures for RSSI/SNR enrichment
type ClientResponse struct {
	TotalCount int          `json:"totalCount"`
	HasMore    bool         `json:"hasMore"`
	FirstIndex int          `json:"firstIndex"`
	List       []ClientInfo `json:"list"`
}

type ClientInfo struct {
	APMac     string `json:"apMac"`
	ClientMac string `json:"clientMac"`
	RSSI      int    `json:"rssi"`
	SNR       int    `json:"snr"`
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
	DeviceName    string  `json:"deviceName"`
	APMAC         string  `json:"apMac"`
	IP            string  `json:"ip"`
	ZoneName      string  `json:"zoneName"`
	NumClients    int     `json:"numClients"`
	NumClients24G int     `json:"numClients24G"`
	NumClients5G  int     `json:"numClients5G"`
	NumClients6G  int     `json:"numClients6G"`
	Airtime24G    float64 `json:"airtime24G"`
	Airtime5G     float64 `json:"airtime5G"`
	Airtime6G     float64 `json:"airtime6G"`
	POEPortStatus string  `json:"poePortStatus,omitempty"` // POE port status (e.g., "100Mbps")

	// Client-derived metrics (enriched from client data)
	RSSI *int `json:"rssi,omitempty"` // Average RSSI from first client (positive value)
	SNR  *int `json:"snr,omitempty"`  // Average SNR from first client

	// Client percentage metrics for RSSI and SNR
	RSSIPercentBelow74 *float64 `json:"rssiPercentBelow74,omitempty"` // Percentage of clients < -74 dBm
	RSSIPercentBelow78 *float64 `json:"rssiPercentBelow78,omitempty"` // Percentage of clients < -78 dBm
	RSSIPercentBelow80 *float64 `json:"rssiPercentBelow80,omitempty"` // Percentage of clients < -80 dBm
	SNRPercentBelow15  *float64 `json:"snrPercentBelow15,omitempty"`  // Percentage of clients < -15 dBm
	SNRPercentBelow18  *float64 `json:"snrPercentBelow18,omitempty"`  // Percentage of clients < -18 dBm
	SNRPercentBelow20  *float64 `json:"snrPercentBelow20,omitempty"`  // Percentage of clients < -20 dBm
}

// InsightFinder data structure
type MetricData struct {
	Timestamp     int64                  `json:"timestamp"`
	InstanceName  string                 `json:"instanceName"`
	Data          map[string]interface{} `json:"data"`
	Zone          string                 `json:"zone,omitempty"`
	ComponentName string                 `json:"componentName,omitempty"`
	IP            string                 `json:"ip,omitempty"`
}

// Convert AP detail to metric data with filtering
func (ap *APDetail) ToMetricData(componentNameAsAP bool, filter MetricFilter) *MetricData {
	cleanDeviceName := cleanDeviceName(ap.DeviceName)
	componentName := ""
	if componentNameAsAP {
		componentName = "AP"
	}

	metric := &MetricData{
		Timestamp:     time.Now().Unix(),
		InstanceName:  cleanDeviceName,
		Data:          map[string]interface{}{},
		Zone:          ap.ZoneName,
		ComponentName: componentName,
		IP:            ap.IP,
	}

	// Add client count metrics based on filter configuration
	if filter.IsNumClientsTotal() {
		metric.Data["Num Clients Total"] = ap.NumClients
	}
	if filter.IsNumClients24G() {
		metric.Data["Num Clients 24G"] = ap.NumClients24G
	}
	if filter.IsNumClients5G() {
		metric.Data["Num Clients 5G"] = ap.NumClients5G
	}
	if filter.IsNumClients6G() {
		metric.Data["Num Clients 6G"] = ap.NumClients6G
	}

	// Add airtime metrics based on filter configuration
	if filter.IsAirtime24G() {
		metric.Data["Airtime 24G Percent"] = ap.Airtime24G
	}
	if filter.IsAirtime5G() {
		metric.Data["Airtime 5G Percent"] = ap.Airtime5G
	}
	if filter.IsAirtime6G() {
		metric.Data["Airtime 6G Percent"] = ap.Airtime6G
	}

	// Add airtime metrics with client threshold (only include airtime if clients > 35)
	if filter.IsAirtime24GClientsOver35() {
		if ap.NumClients24G > 35 {
			metric.Data["Airtime 24G Clients > 35"] = ap.Airtime24G
		} else {
			metric.Data["Airtime 24G Clients > 35"] = 0.0
		}
	}
	if filter.IsAirtime5GClientsOver35() {
		if ap.NumClients5G > 35 {
			metric.Data["Airtime 5G Clients > 35"] = ap.Airtime5G
		} else {
			metric.Data["Airtime 5G Clients > 35"] = 0.0
		}
	}
	if filter.IsAirtime6GClientsOver35() {
		if ap.NumClients6G > 35 {
			metric.Data["Airtime 6G Clients > 35"] = ap.Airtime6G
		} else {
			metric.Data["Airtime 6G Clients > 35"] = 0.0
		}
	}

	// Add client-derived metrics based on filter configuration
	if ap.RSSI != nil && filter.IsRSSIAvg() {
		metric.Data["RSSI Avg"] = *ap.RSSI
	}
	if ap.SNR != nil && filter.IsSNRAvg() {
		metric.Data["SNR Avg"] = *ap.SNR
	}

	// Add RSSI percentage metrics based on filter configuration
	if ap.RSSIPercentBelow74 != nil && filter.IsClientsRSSIBelow74() {
		metric.Data["% Clients RSSI < -74 dBm"] = *ap.RSSIPercentBelow74
	}
	if ap.RSSIPercentBelow78 != nil && filter.IsClientsRSSIBelow78() {
		metric.Data["% Clients RSSI < -78 dBm"] = *ap.RSSIPercentBelow78
	}
	if ap.RSSIPercentBelow80 != nil && filter.IsClientsRSSIBelow80() {
		metric.Data["% Clients RSSI < -80 dBm"] = *ap.RSSIPercentBelow80
	}

	// Add SNR percentage metrics based on filter configuration
	if ap.SNRPercentBelow15 != nil && filter.IsClientsSNRBelow15() {
		metric.Data["% Clients SNR < 15 dBm"] = *ap.SNRPercentBelow15
	}
	if ap.SNRPercentBelow18 != nil && filter.IsClientsSNRBelow18() {
		metric.Data["% Clients SNR < 18 dBm"] = *ap.SNRPercentBelow18
	}
	if ap.SNRPercentBelow20 != nil && filter.IsClientsSNRBelow20() {
		metric.Data["% Clients SNR < 20 dBm"] = *ap.SNRPercentBelow20
	}

	// Add Ethernet Status Mbps metric based on filter configuration
	if ap.POEPortStatus != "" && filter.IsEthernetStatusMbps() {
		if mbpsValue := ExtractMbpsFromPOEPortStatus(ap.POEPortStatus); mbpsValue != nil {
			metric.Data["Ethernet Status Mbps"] = *mbpsValue
		}
	}

	return metric
}
