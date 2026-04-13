package insightfinder

import (
	"net/http"

	"github.com/insightfinder/splunk-forwarder/configs"
)

// Service holds the InsightFinder HTTP client and project settings.
type Service struct {
	config           configs.InsightFinderConfig
	httpClient       *http.Client
	ProjectName      string
	LogProjectName   string
	SystemName       string
	CloudType        string
	InstanceType     string
	ProjectType      string
	DataType         string
	Container        bool
	InsightAgentType string
	SamplingInterval uint
}

// SplunkEventSlim is the normalised, package-neutral form of a Splunk event
// that the worker passes to the InsightFinder service.
// Fields contains all keys returned by Splunk (_raw, _time, host, sourcetype,
// index, source, and any extra fields) so they can be forwarded as structured
// JSON and used for dynamic tag / component resolution.
type SplunkEventSlim struct {
	TimestampMs int64                  // Unix milliseconds derived from Splunk _time
	Fields      map[string]interface{} // all Splunk fields, including _raw
}

// LogData is the per-event object sent inside logDataList.
type LogData struct {
	TimeStamp     int64       `json:"timestamp"`
	Tag           string      `json:"tag"`           // instance name
	ComponentName string      `json:"componentName"` // component
	Data          interface{} `json:"data"`          // full event as JSON object
}

// CheckAndAddCustomProjectRequest is the form payload for project creation/check.
type CheckAndAddCustomProjectRequest struct {
	Operation        string `json:"operation,omitempty"`
	UserName         string `json:"userName,omitempty"`
	LicenseKey       string `json:"licenseKey,omitempty"`
	ProjectName      string `json:"projectName,omitempty"`
	SystemName       string `json:"systemName,omitempty"`
	InstanceType     string `json:"instanceType,omitempty"`
	ProjectCloudType string `json:"projectCloudType,omitempty"`
	DataType         string `json:"dataType,omitempty"`
	InsightAgentType string `json:"insightAgentType,omitempty"`
	SamplingInterval int    `json:"samplingInterval,omitempty"`
}

// CheckAndAddCustomProjectResponse is the JSON response from the project endpoint.
type CheckAndAddCustomProjectResponse struct {
	IsSuccess      bool   `json:"success"`
	IsProjectExist bool   `json:"isProjectExist"`
	Message        string `json:"message"`
}
