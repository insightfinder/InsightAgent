package insightfinder

// DataMessage represents a message collected from a data source by
// an InsightFinder agent collector. For metric data, the message
// contains one metric value.
type DataMessage struct {
	Timestamp     string
	ComponentName string
	Instance      string
	MetricName    string
	HostId        string
	Value         string
}

type MetricDataPoint struct {
	MetricName string  `json:"m" validate:"required"`
	Value      float64 `json:"v" validate:"required"`
	GroupId    string  `json:"g,omitempty"`
}

type K8Identity struct {
	HostId string `json:"hostId,omitempty"`
	PodId  string `json:"podId,omitempty"`
}

type DataInTimestamp struct {
	TimeStamp        int64             `json:"t" validate:"required"`
	MetricDataPoints []MetricDataPoint `json:"metricDataPointSet" validate:"required"`
	K8Identity       *K8Identity       `json:"k,omitempty"`
}

type InstanceData struct {
	InstanceName       string                    `json:"in" validate:"required"`
	ComponentName      string                    `json:"cn,omitempty"`
	DataInTimestampMap map[int64]DataInTimestamp `json:"dit" validate:"required"`
}

type MetricDataReceivePayload struct {
	ProjectName      string                  `json:"projectName" validate:"required"`
	UserName         string                  `json:"userName" validate:"required"`
	InstanceDataMap  map[string]InstanceData `json:"idm" validate:"required"`
	SystemName       string                  `json:"systemName,omitempty"`
	MinTimestamp     int64                   `json:"mi,omitempty"`
	MaxTimestamp     int64                   `json:"ma,omitempty"`
	InsightAgentType string                  `json:"iat,omitempty"`
	SamplingInterval string                  `json:"si,omitempty"`
	CloudType        string                  `json:"ct,omitempty"`
}

type IFMetricPostRequestPayload struct {
	LicenseKey string                   `json:"licenseKey" validate:"required"`
	UserName   string                   `json:"userName" validate:"required"`
	Data       MetricDataReceivePayload `json:"data" validate:"required"`
}
