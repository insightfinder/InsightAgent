package main

type MetricDataPoint struct {
	MetricName string  `json:"m,omitempty" validate:"required"`
	Value      float64 `json:"v,omitempty" validate:"required"`
	GroupId    string  `json:"g,omitempty"`
}

type DataInTimestamp struct {
	TimeStamp        int64             `json:"t" validate:"required"`
	MetricDataPoints []MetricDataPoint `json:"metricDataPointSet" validate:"required"`
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
	MinTimestamp     int64                   `json:"mi,omitempty"`
	MaxTimestamp     int64                   `json:"ma,omitempty"`
	InsightAgentType string                  `json:"iat,omitempty"`
	SamplingInterval string                  `json:"si,omitempty"`
}

// MetricDataReceivePayload
// String projectName, String userName, long minTimestamp,
//       long maxTimestamp, String insightAgentType, String samplingInterval,
//       Map<String, InstanceData> instanceDataMap, MetricReplayStatusModel metricReplayStatus
// @SerializedName(value = "i", alternate = {"isTimestampConverted"})
//   private final boolean isTimestampConverted = false;
//   @SerializedName(value = "mi", alternate = {"minTimestamp"})
//   private final long minTimestamp;
//   @SerializedName(value = "ma", alternate = {"maxTimestamp"})
//   private final long maxTimestamp;
//   @SerializedName(value = "iat", alternate = {"insightAgentType"})
//   private final String insightAgentType;
//   @SerializedName(value = "si", alternate = {"samplingInterval"})
//   private final String samplingInterval;
//   @SerializedName(value = "idm", alternate = {"instanceDataMap"})
//   private Map<String, InstanceData> instanceDataMap;
//   @SerializedName(value = "mrs", alternate = {"metricReplayStatus"})
//   private final MetricReplayStatusModel metricReplayStatus;
