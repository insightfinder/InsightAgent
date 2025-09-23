package tarana

// Authentication structures
type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type LoginResponse struct {
	Data  LoginData `json:"data"`
	Error string    `json:"error"`
}

type LoginData struct {
	Session           interface{} `json:"session"`
	UserID            string      `json:"userId"`
	AccessToken       string      `json:"accessToken"`
	ChallengeResult   interface{} `json:"challengeResult"`
	IDToken           string      `json:"idToken"`
	RefreshToken      string      `json:"refreshToken"`
	MfaSecret         interface{} `json:"mfaSecret"`
	ExpiryTimeSeconds int         `json:"expiryTimeSeconds"`
	Message           interface{} `json:"message"`
	IDPToken          bool        `json:"idpToken"`
}

type RefreshTokenResponse struct {
	Data  RefreshTokenData `json:"data"`
	Error string           `json:"error"`
}

type RefreshTokenData struct {
	Session           interface{} `json:"session"`
	UserID            *string     `json:"userId"`
	AccessToken       string      `json:"accessToken"`
	ChallengeResult   interface{} `json:"challengeResult"`
	IDToken           string      `json:"idToken"`
	RefreshToken      *string     `json:"refreshToken"`
	MfaSecret         interface{} `json:"mfaSecret"`
	ExpiryTimeSeconds int         `json:"expiryTimeSeconds"`
	Message           interface{} `json:"message"`
	IDPToken          bool        `json:"idpToken"`
}

// Device search structures
type DeviceSearchRequest struct {
	IDs          []int               `json:"ids"`
	DeviceFilter DeviceFilterRequest `json:"deviceFilter"`
}

type DeviceFilterRequest struct {
	// Add any device filter fields as needed
}

type DeviceSearchResponse struct {
	Data  DeviceSearchData `json:"data"`
	Error string           `json:"error"`
}

type DeviceSearchData struct {
	Items      []Device `json:"items"`
	Count      int      `json:"count"`
	Offset     int      `json:"offset"`
	TotalCount int      `json:"totalCount"`
}

type Device struct {
	SerialNumber string `json:"serialNumber"`
	Type         string `json:"type"`
	IP           string `json:"ip"`
	HostName     string `json:"hostName"`
}

// KPI/Metrics structures
type MetricsRequest struct {
	Filter     MetricsFilter `json:"filter"`
	KPIs       []string      `json:"kpis"`
	PageNumber int           `json:"page_number"`
	PageSize   int           `json:"page_size"`
}

type MetricsFilter struct {
	ResidentialNodes []string `json:"residential_nodes"`
}

type MetricsResponse struct {
	Data  MetricsData `json:"data"`
	Error string      `json:"error"`
}

type MetricsData struct {
	Items           []DeviceMetrics  `json:"items"`
	Count           int              `json:"count"`
	TotalCount      int              `json:"totalCount"`
	Description     string           `json:"description"`
	UnavailableKPIs []UnavailableKPI `json:"unavailable_kpis"`
}

type DeviceMetrics struct {
	DeviceID string `json:"device_id"`
	KPIs     []KPI  `json:"kpis"`
}

type KPI struct {
	KPI               string  `json:"kpi"`
	Value             float64 `json:"value"`
	Time              int64   `json:"time"`
	SampleAggregation string  `json:"sample_aggregation"`
}

type UnavailableKPI struct {
	KPI     string `json:"kpi"`
	Message string `json:"message"`
}

// Alarm/Logs structures
type AlarmRequest struct {
	AlarmsFilters []AlarmFilter `json:"alarms-filters"`
	Filter        RegionFilter  `json:"filter"`
	From          int           `json:"from"`
	Size          int           `json:"size"`
	Sort          []SortConfig  `json:"sort"`
}

type AlarmFilter struct {
	Term      string   `json:"term"`
	Type      string   `json:"type"`
	TermValue []string `json:"termValue"`
}

type RegionFilter struct {
	Regions []int `json:"regions"`
}

type SortConfig struct {
	Field string `json:"field"`
	Order string `json:"order"`
}

type AlarmResponse struct {
	Data  AlarmData `json:"data"`
	Error string    `json:"error"`
}

type AlarmData struct {
	Details     []AlarmDetail `json:"details"`
	Count       int           `json:"count"`
	Offset      int           `json:"offset"`
	Total       int           `json:"total"`
	Description string        `json:"description"`
}

type AlarmDetail struct {
	DeviceIP              string      `json:"deviceIp"`
	DeviceID              string      `json:"device-id"`
	DeviceIDFull          string      `json:"deviceId"`
	Operator              string      `json:"operator"`
	Band                  string      `json:"band"`
	ID                    string      `json:"id"`
	Text                  string      `json:"text"`
	TimeCleared           int64       `json:"time-cleared"`
	TimeCreated           int64       `json:"time-created"`
	OperatorID            int         `json:"operatorId"`
	Sector                string      `json:"sector"`
	DeviceHostName        string      `json:"deviceHostName"`
	GenerateSnapshot      string      `json:"generate_snapshot"`
	MaxThreshold          string      `json:"max_threshold"`
	SectorID              int         `json:"sectorId"`
	AlarmKey              string      `json:"alarm-key"`
	Resource              string      `json:"resource"`
	BootID                string      `json:"bootId"`
	TypeID                int         `json:"type-id"`
	BNID                  string      `json:"bn-id"`
	CellID                int         `json:"cellId"`
	DeviceSerialNumber    string      `json:"deviceSerialNumber"`
	Market                string      `json:"market"`
	MinThreshold          string      `json:"min_threshold"`
	MacAddress            string      `json:"macAddress"`
	RNID                  string      `json:"rn-id"`
	CellNetworkID         int         `json:"cellNetworkId"`
	DevicePlatform        string      `json:"device_platform"`
	Region                string      `json:"region"`
	SoftwareVersion       string      `json:"softwareVersion"`
	Status                string      `json:"status"`
	BootReason            string      `json:"bootReason"`
	Access                string      `json:"access"`
	RaiseCount            int         `json:"raise-count"`
	DisplayResource       string      `json:"display-resource"`
	Cell                  string      `json:"cell"`
	MarketID              int         `json:"marketId"`
	Hysteresis            string      `json:"hysteresis"`
	MaxSendUpdtTokens     string      `json:"max_send_updt_tokens"`
	ExtensionID           string      `json:"extension-id"`
	SendUpdtTokRefillQty  string      `json:"send_updt_tok_refill_qty"`
	SectorNetworkID       int         `json:"sectorNetworkId"`
	MasterSoftwareVersion string      `json:"masterSoftwareVersion"`
	Timestamp             int64       `json:"timestamp"`
	Severity              int         `json:"severity"`
	WriteTime             string      `json:"writeTime"`
	BootTimeSeconds       int64       `json:"bootTimeSeconds"`
	Retailer              string      `json:"retailer"`
	HasThresholds         string      `json:"has_thresholds"`
	RetailerID            int         `json:"retailerId"`
	MSTime                string      `json:"msTime"`
	MasterID              string      `json:"masterId"`
	Site                  string      `json:"site"`
	AcknowledgementNote   interface{} `json:"acknowledgement-note"`
	RegionID              int         `json:"regionId"`
	TimestampNS           int64       `json:"timestampns"`
	SiteID                int         `json:"siteId"`
	DisplayID             string      `json:"display-id"`
	DeviceTimestamp       int64       `json:"device-timestamp"`
	Category              string      `json:"category"`
	RadioType             string      `json:"radioType"`
	RaiseAction           string      `json:"raise_action"`
}
