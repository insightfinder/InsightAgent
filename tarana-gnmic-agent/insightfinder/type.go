package insightfinder

import (
	"net/http"

	"github.com/tarana/gnmic-agent/config"
)

type Service struct {
	config           config.InsightFinderConfig
	httpClient       *http.Client
	ProjectName      string
	SystemName       string
	CloudType        string
	InstanceType     string
	ProjectType      string // "Metric", "Log", "Trace", "Deployment", "Alert", "Incident"
	DataType         string
	Container        bool
	InsightAgentType string
	SamplingInterval uint // In seconds
}

// InsightFinder data structures (matching v2 API format)
type MetricDataPoint struct {
	MetricName string  `json:"m"`
	Value      float64 `json:"v"`
	GroupId    string  `json:"g,omitempty"`
}

type DataInTimestamp struct {
	TimeStamp        int64              `json:"t"`
	MetricDataPoints *[]MetricDataPoint `json:"metricDataPointSet"`
}

type InstanceData struct {
	InstanceName       string                    `json:"in"`
	ComponentName      string                    `json:"cn,omitempty"`
	DataInTimestampMap map[int64]DataInTimestamp `json:"dit"`
	Zone               string                    `json:"z,omitempty"`
	IP                 string                    `json:"i,omitempty"`
}

type MetricDataReceivePayload struct {
	ProjectName      string                  `json:"projectName"`
	UserName         string                  `json:"userName"`
	InstanceDataMap  map[string]InstanceData `json:"idm"`
	SystemName       string                  `json:"systemName,omitempty"`
	MinTimestamp     int64                   `json:"mi,omitempty"`
	MaxTimestamp     int64                   `json:"ma,omitempty"`
	InsightAgentType string                  `json:"iat,omitempty"`
	SamplingInterval string                  `json:"si,omitempty"`
	CloudType        string                  `json:"ct,omitempty"`
}

type IFMetricPostRequestPayload struct {
	LicenseKey string                   `json:"licenseKey"`
	UserName   string                   `json:"userName"`
	Data       MetricDataReceivePayload `json:"data"`
}

// Project creation/check structures
type CheckAndAddCustomProjectRequest struct {
	Operation        string `json:"operation,omitempty" url:"operation,omitempty"`
	UserName         string `json:"userName,omitempty" url:"userName,omitempty"`
	LicenseKey       string `json:"licenseKey,omitempty" url:"licenseKey,omitempty"`
	ProjectName      string `json:"projectName,omitempty" url:"projectName,omitempty"`
	SystemName       string `json:"systemName,omitempty" url:"systemName,omitempty"`
	InstanceType     string `json:"instanceType,omitempty" url:"instanceType,omitempty"`
	ProjectCloudType string `json:"projectCloudType,omitempty" url:"projectCloudType,omitempty"`
	DataType         string `json:"dataType,omitempty" url:"dataType,omitempty"`
	InsightAgentType string `json:"insightAgentType,omitempty" url:"insightAgentType,omitempty"`
	SamplingInterval int    `json:"samplingInterval,omitempty" url:"samplingInterval,omitempty"`
}

type CheckAndAddCustomProjectResponse struct {
	IsSuccess      bool   `json:"success"`
	IsProjectExist bool   `json:"isProjectExist"`
	Message        string `json:"message"`
}

// Log data structures
type LogData struct {
	TimeStamp     int64       `json:"timestamp"`
	Tag           string      `json:"tag"`
	ComponentName string      `json:"componentName"`
	Data          interface{} `json:"data"`
}

type LogDataReceivePayload struct {
	UserName         string    `json:"userName"`
	LicenseKey       string    `json:"licenseKey"`
	ProjectName      string    `json:"projectName"`
	SystemName       string    `json:"systemName"`
	InsightAgentType string    `json:"insightAgentType"`
	LogDataList      []LogData `json:"logDataList"`
}
