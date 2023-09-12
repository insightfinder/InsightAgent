package insightfinder

type MetricDataPoint struct {
	MetricName string  `json:"m" validate:"required"`
	Value      float64 `json:"v" validate:"required"`
	GroupId    string  `json:"g,omitempty"`
}

type K8Identity struct {
	HostId string `json:"hostId" validate:"required"`
	PodId  string `json:"podId" validate:"required"`
}

type DataInTimestamp struct {
	TimeStamp        int64             `json:"t" validate:"required"`
	MetricDataPoints []MetricDataPoint `json:"metricDataPointSet" validate:"required"`
	K8Identity       K8Identity        `json:"k,omitempty"`
}

type InstanceData struct {
	InstanceName       string                    `json:"in" validate:"required"`
	ComponentName      string                    `json:"cn" validate:"required"`
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
}

type IFMetricPostRequestPayload struct {
	LicenseKey string                   `json:"licenseKey" validate:"required"`
	UserName   string                   `json:"userName" validate:"required"`
	Data       MetricDataReceivePayload `json:"data" validate:"required"`
}

type AuthRequest struct {
	Password string `json:"password" validate:"required"`
	UserName string `json:"userName"`
}
