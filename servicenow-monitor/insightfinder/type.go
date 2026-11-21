package insightfinder

import (
	"net/http"

	config "github.com/insightfinder/servicenow-monitor/configs"
)

type Service struct {
	config     config.InsightFinderConfig
	httpClient *http.Client
}

// MetricData is one instance's metric values at a timestamp (epoch ms).
type MetricData struct {
	InstanceName  string
	ComponentName string
	Timestamp     int64
	Data          map[string]float64
}

// InsightFinder data structures (matching v2 API format)
type MetricDataPoint struct {
	MetricName string  `json:"m"`
	Value      float64 `json:"v"`
}

type DataInTimestamp struct {
	TimeStamp        int64             `json:"t"`
	MetricDataPoints []MetricDataPoint `json:"metricDataPointSet"`
}

type InstanceData struct {
	InstanceName        string                    `json:"in"`
	DataInTimestampMap  map[int64]DataInTimestamp `json:"dit"`
	InstanceMetadataStr string                    `json:"im,omitempty"`
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

type CheckAndAddCustomProjectResponse struct {
	IsSuccess      bool   `json:"success"`
	IsProjectExist bool   `json:"isProjectExist"`
	Message        string `json:"message"`
}
