package main

type LogData struct {
	TimeStamp     int64       `json:"timestamp" validate:"required"`
	Tag           string      `json:"tag" validate:"required"`
	Data          interface{} `json:"data" validate:"required"`
	ComponentName string      `json:"componentName,omitempty"`
}

type LogDataReceivePayload struct {
	UserName         string    `json:"userName" validate:"required"`
	ProjectName      string    `json:"projectName" validate:"required"`
	LicenseKey       string    `json:"licenseKey" validate:"required"`
	LogDataList      []LogData `json:"metricData" validate:"required"`
	InsightAgentType string    `json:"agentType" validate:"required"`
	SystemName       string    `json:"systemName,omitempty"`
	MinTimestamp     int64     `json:"minTimestamp,omitempty"`
	MaxTimestamp     int64     `json:"maxTimestamp,omitempty"`
}
