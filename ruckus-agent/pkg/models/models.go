package models

import "time"

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

// Convert AP detail to metric data
func (ap *APDetail) ToMetricData(componentNameAsAP bool) *MetricData {
	cleanDeviceName := cleanDeviceName(ap.DeviceName)
	componentName := ""
	if componentNameAsAP {
		componentName = "AP"
	}

	metric := &MetricData{
		Timestamp:    time.Now().Unix(),
		InstanceName: cleanDeviceName,
		Data: map[string]interface{}{
			"Num Clients Total":   ap.NumClients,
			"Num Clients 24G":     ap.NumClients24G,
			"Num Clients 5G":      ap.NumClients5G,
			"Num Clients 6G":      ap.NumClients6G,
			"Airtime 24G Percent": ap.Airtime24G,
			"Airtime 5G Percent":  ap.Airtime5G,
			"Airtime 6G Percent":  ap.Airtime6G,
		},
		Zone:          ap.ZoneName,
		ComponentName: componentName,
		IP:            ap.IP,
	}

	// Add client-derived metrics if available
	if ap.RSSI != nil {
		metric.Data["RSSI Avg"] = *ap.RSSI
	}
	if ap.SNR != nil {
		metric.Data["SNR Avg"] = *ap.SNR
	}

	// Add RSSI percentage metrics
	if ap.RSSIPercentBelow74 != nil {
		metric.Data["RSSI Percent Below -74dBm"] = *ap.RSSIPercentBelow74
	}
	if ap.RSSIPercentBelow78 != nil {
		metric.Data["RSSI Percent Below -78dBm"] = *ap.RSSIPercentBelow78
	}
	if ap.RSSIPercentBelow80 != nil {
		metric.Data["RSSI Percent Below -80dBm"] = *ap.RSSIPercentBelow80
	}

	// Add SNR percentage metrics
	if ap.SNRPercentBelow15 != nil {
		metric.Data["SNR Percent Below 15dBm"] = *ap.SNRPercentBelow15
	}
	if ap.SNRPercentBelow18 != nil {
		metric.Data["SNR Percent Below 18dBm"] = *ap.SNRPercentBelow18
	}
	if ap.SNRPercentBelow20 != nil {
		metric.Data["SNR Percent Below 20dBm"] = *ap.SNRPercentBelow20
	}

	return metric
}
