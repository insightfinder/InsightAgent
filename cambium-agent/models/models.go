package models

// MetricData represents the structure for metric data that will be sent to InsightFinder
type MetricData struct {
	Timestamp     int64                  `json:"timestamp"`
	InstanceName  string                 `json:"instanceName"`
	ComponentName string                 `json:"componentName,omitempty"`
	Data          map[string]interface{} `json:"data"`
	Zone          string                 `json:"zone,omitempty"`
	IP            string                 `json:"ip,omitempty"`
}

// Device represents a device from the Cambium API response
type Device struct {
	MAC    string      `json:"mac"`
	Name   string      `json:"name"`
	Sys    SystemInfo  `json:"sys"`
	Net    NetworkInfo `json:"net"`
	Config ConfigInfo  `json:"config"`
	Cfg    CfgInfo     `json:"cfg"`
	Mode   string      `json:"mode"`
	Nid    string      `json:"nid"`
}

type SystemInfo struct {
	Online bool    `json:"online"`
	Mem    float64 `json:"mem"`
	CPU    float64 `json:"cpu"`
}

type NetworkInfo struct {
	WAN string `json:"wan,omitempty"`
	IP  string `json:"ip,omitempty"`
}

type ConfigInfo struct {
	Profile string `json:"profile"`
}

type CfgInfo struct {
	Name string `json:"name"`
}

// DevicesResponse represents the API response for devices
type DevicesResponse struct {
	Data struct {
		Metadata struct {
			TotalCount int `json:"totalCount"`
			Offset     int `json:"offset"`
			Limit      int `json:"limit"`
		} `json:"_metadata"`
		Devices []Device `json:"devices"`
	} `json:"data"`
	STime int64 `json:"sTime"`
}

// Radio represents radio data from the stats API
type Radio struct {
	// Common fields
	Band    string  `json:"band"`
	Mus     int     `json:"mus"`
	TotalCu float64 `json:"total_cu"`

	// Channel interface{} `json:"channel"` // Can be string or int
	// DlTPut  float64     `json:"dlTPut"`
	// UlTPut  float64     `json:"ulTPut"`
	// Nf      float64     `json:"nf"`

	// Additional fields for different radio types
	// Id        interface{} `json:"id"` // Can be string or int
	// Mac       string      `json:"mac"`
	// Pmac      string      `json:"pmac"`
	// Cid       string      `json:"cid"`
	// State     string      `json:"state"`
	// ChWidth   string      `json:"chWidth"`
	// ChanIf    int         `json:"chan_if"`
	// ChannelUt int         `json:"channel_ut"`
	// MMus      int         `json:"mMus"`
	// McRate    string      `json:"mcRate"`
	// MeshState string      `json:"meshState"`
	// Nav       int         `json:"nav"`
	// Per       int         `json:"per"`
	// Pow       int         `json:"pow"`
	// RfUtil    int         `json:"rfUtil"`
	// Rfqlt     int         `json:"rfqlt"`
	// Rx        float64     `json:"rx"`
	// RxAvg     int         `json:"rxAvg"`
	// RxMax     int         `json:"rxMax"`
	// RxMin     int         `json:"rxMin"`
	// RxPkts    int64       `json:"rxPkts"`
	// RxCu      int         `json:"rx_cu"`
	// Ts        int64       `json:"ts"`
	// Tx        float64     `json:"tx"`
	// TxAvg     int         `json:"txAvg"`
	// TxMax     int         `json:"txMax"`
	// TxMin     int         `json:"txMin"`
	// TxPkts    int64       `json:"txPkts"`
	// TxCu      int         `json:"tx_cu"`
	// UcRates   string      `json:"ucRates"`
	// Wlans     int         `json:"wlans"`
	// BusyCu    int         `json:"busy_cu"`

	// // Fields for other radio configurations
	// BaseBandTemp           int    `json:"baseBandTemp,omitempty"`
	// ConfiguredTddSlotRatio string `json:"configuredTddSlotRatio,omitempty"`
	// CurrentTddSlotRatio    string `json:"currentTddSlotRatio,omitempty"`
	// ErrAssoc               int    `json:"errAssoc,omitempty"`
	// NumSwitches            int    `json:"numSwitches,omitempty"`
	// Polarity               int    `json:"polarity,omitempty"`
	// RfTile0Temp            int    `json:"rfTile0Temp,omitempty"`
	// RfTile1Temp            int    `json:"rfTile1Temp,omitempty"`
	// RfTile2Temp            int    `json:"rfTile2Temp,omitempty"`
	// RfTile3Temp            int    `json:"rfTile3Temp,omitempty"`
	// Security               int    `json:"security,omitempty"`
	// SetErrChannel          int    `json:"setErrChannel,omitempty"`
	// SyncModeGps            int    `json:"syncModeGps,omitempty"`
	// SyncModeRf             int    `json:"syncModeRf,omitempty"`
}

// RadiosResponse represents the API response for radio stats
type RadiosResponse struct {
	Data struct {
		Metadata struct {
			Limit  int `json:"limit"`
			Offset int `json:"offset"`
			Total  int `json:"total"`
		} `json:"_metadata"`
		Radios []Radio `json:"radios"`
	} `json:"data"`
	STime int64 `json:"sTime"`
}

// Link represents a single link in the E2E data
type Link struct {
	RSSI  int `json:"rssi"`
	SNR   int `json:"snr"`
	RxMCS int `json:"rxMcs"`

	// ZMAC          string `json:"zmac"`
	// AMAC          string `json:"amac"`
	// EIRP          int    `json:"eirp"`
	// LinkAvailable int    `json:"linkAvailable"`
	// Name          string `json:"name"`
	// TS            int64  `json:"ts"`
	// TxMCS         int    `json:"txMcs"`
	// Direction     int    `json:"direction"`
	// ID            string `json:"_id"`
	// ANode         string `json:"aNode"`
	// ZNode         string `json:"zNode"`
}

// E2EData represents the API response for E2E link data
type E2EData struct {
	Data struct {
		Metadata struct {
			TotalCount int `json:"totalCount"`
			Limit      int `json:"limit"`
			Offset     int `json:"offset"`
		} `json:"_metadata"`
		Links []Link `json:"links"`
	} `json:"data"`
	STime int64 `json:"sTime"`
}
