package positron

import (
	"net/http"
	"sync"
	"time"

	config "github.com/insightfinder/positron-agent/configs"
)

type Service struct {
	Config        config.PositronConfig
	HttpClient    *http.Client
	BaseURL       string
	SessionMutex  sync.RWMutex
	SessionExpiry time.Duration
	// LastSentAlarmReceived stores the latest 'received' timestamp that was
	// already returned by GetAlarms to avoid duplicates across polling cycles.
	LastSentAlarmReceived time.Time
}

// Endpoint represents an endpoint from the API response
type Endpoint struct {
	// ID                  string `json:"id"`
	// MacAddress          string `json:"macAddress"`
	// ConfEndpointID      int    `json:"confEndpointId"`
	ConfEndpointName string `json:"confEndpointName"`
	// ConfPortIfIndex     string `json:"confPortIfIndex"`
	// ConfAutoPort        bool   `json:"confAutoPort"`
	// DetectedPortIfIndex string `json:"detectedPortIfIndex"`
	// ConfUserID          int    `json:"confUserId"`
	// ConfUserName        string `json:"confUserName"`
	// ConfUserUid         int    `json:"confUserUid"`
	// ConfBwProfileID     int    `json:"confBwProfileId"`
	// ConfBwProfileName   string `json:"confBwProfileName"`
	// ConfBwProfileUid    int    `json:"confBwProfileUid"`
	// State               string `json:"state"`
	// ModelType           string `json:"modelType"`
	// ModelString         string `json:"modelString"`
	// FwMismatch          bool   `json:"fwMismatch"`
	// Alive               bool   `json:"alive"`
	// HwProduct           string `json:"hwProduct"`
	// SerialNumber        string `json:"serialNumber"`
	// UpTime              string `json:"upTime"`
	// FwVersion           string `json:"fwVersion"`
	// XputIndicator       int    `json:"xputIndicator"`
	// Mode                string `json:"mode"`
	// WireLengthMeters    int    `json:"wireLengthMeters"`
	// WireLengthFeet      int    `json:"wireLengthFeet"`
	RxPhyRate int `json:"rxPhyRate"`
	TxPhyRate int `json:"txPhyRate"`
	// RxAllocBands        int    `json:"rxAllocBands"`
	// TxAllocBands        int    `json:"txAllocBands"`
	RxMaxXput int `json:"rxMaxXput"`
	TxMaxXput int `json:"txMaxXput"`
	// RxUsage   int `json:"rxUsage"`
	// TxUsage   int `json:"txUsage"`
	// DeviceName          string `json:"deviceName"`
	// CreationDate        string `json:"creationDate"`
	// LastModifiedDate    string `json:"lastModifiedDate"`
}

// Device represents a device from the device list API
type Device struct {
	Name string `json:"name"`
	// SerialNumber              string  `json:"serialNumber"`
	IPAddress string `json:"ipAddress"`
	// ProductClass              string  `json:"productClass"`
	// SoftwareVersion           string  `json:"softwareVersion"`
	// SyncError                 *string `json:"syncError"`
	// NtpServer1                string  `json:"ntpServer1"`
	// NtpServer2                string  `json:"ntpServer2"`
	// NtpServer3                *string `json:"ntpServer3"`
	// NtpServer4                *string `json:"ntpServer4"`
	// NtpServer5                *string `json:"ntpServer5"`
	// Timezone                  *string `json:"timezone"`
	// SummerTime                *string `json:"summerTime"`
	// Asy                       string  `json:"asy"`
	// Revision                  string  `json:"revision"`
	Ports       int `json:"ports"`
	Endpoints   int `json:"endpoints"`
	Subscribers int `json:"subscribers"`
	Bandwidths  int `json:"bandwidths"`
	// Uptime                    string  `json:"uptime"`
	// LastAnnouncement          string  `json:"lastAnnouncement"`
	// LastModifiedDate          string  `json:"lastModifiedDate"`
	// Sync                      *string `json:"sync"`
	// FirmwareUpgradeInProgress bool    `json:"firmwareUpgradeInProgress"`
}

// Alarm represents an alarm from the alarm list API
type Alarm struct {
	SystemName         string  `json:"systemName"`
	ProductClass       string  `json:"productClass"`
	Severity           string  `json:"severity"`
	Condition          string  `json:"condition"`
	ServiceAffecting   string  `json:"serviceAffecting"`
	Description        string  `json:"description"`
	Occurred           string  `json:"occured"` // Note: API returns "occured" (typo)
	DeviceSerialNumber string  `json:"deviceSerialNumber"`
	Received           string  `json:"received"`
	Cleared            *string `json:"cleared"`
	Details            string  `json:"details"`
}

// API Response structures
type EndpointResponse struct {
	Data    []Endpoint `json:"data"`
	Message string     `json:"message"`
	Status  int        `json:"status"`
}

type DeviceResponse struct {
	Settings struct {
		ServerTime                         string `json:"server_time"`
		DeviceMinutesWarningActive         string `json:"device_minutes_warning_active"`
		GeneralConvertDateWithUserTimezone string `json:"general_convert_date_with_user_timezone"`
		TableDelayMinutesActiveLine        string `json:"table_delay_minutes_active_line"`
		DeviceMinutesConsideredActive      string `json:"device_minutes_considered_active"`
		UserTimezone                       string `json:"user_timezone"`
	} `json:"settings"`
	Data       []Device      `json:"data"`
	ExtraData  []interface{} `json:"extraData"`
	Count      int           `json:"count"`
	Message    string        `json:"message"`
	TotalCount int           `json:"totalCount"`
	Status     int           `json:"status"`
}

type AlarmResponse struct {
	Settings struct {
		ServerTime                         string `json:"server_time"`
		GeneralConvertDateWithUserTimezone string `json:"general_convert_date_with_user_timezone"`
		UserTimezone                       string `json:"user_timezone"`
	} `json:"settings"`
	Data       []Alarm `json:"data"`
	Count      int     `json:"count"`
	Message    string  `json:"message"`
	TotalCount int     `json:"totalCount"`
	Status     int     `json:"status"`
}

// Error response structure
type ErrorResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}
