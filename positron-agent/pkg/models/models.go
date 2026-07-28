package models

// InsightFinder data structure
type MetricData struct {
	Timestamp     int64                  `json:"timestamp"`
	InstanceName  string                 `json:"instanceName"`
	DisplayName   string                 `json:"displayName,omitempty"`
	Data          map[string]interface{} `json:"data"`
	Zone          string                 `json:"zone,omitempty"`
	ComponentName string                 `json:"componentName,omitempty"`
	IP            string                 `json:"ip,omitempty"`
}
