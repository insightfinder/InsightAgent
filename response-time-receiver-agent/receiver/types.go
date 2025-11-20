package receiver

import (
	"encoding/json"
	"fmt"
	"strconv"
)

// AgentType represents the type of agent sending data
type AgentType int

// Agent type constants
const (
	// AgentTypeServiceNowResponse represents ServiceNow response data
	AgentTypeServiceNowResponse AgentType = 0
	// AgentTypeCustom represents custom agent data
	AgentTypeCustom AgentType = 1
	// Additional agent types can be added here (2, 3, etc.)
)

// String returns the string representation of AgentType
func (a AgentType) String() string {
	switch a {
	case AgentTypeServiceNowResponse:
		return "servicenowresponse"
	case AgentTypeCustom:
		return "custom"
	default:
		return "unknown"
	}
}

// UnmarshalJSON implements custom JSON unmarshaling for AgentType
// It accepts both numeric values (0, 1) and string values ("0", "1", "servicenowresponse", "custom")
func (a *AgentType) UnmarshalJSON(data []byte) error {
	// Try to unmarshal as number first
	var num int
	if err := json.Unmarshal(data, &num); err == nil {
		*a = AgentType(num)
		return nil
	}

	// Try to unmarshal as string
	var str string
	if err := json.Unmarshal(data, &str); err != nil {
		return fmt.Errorf("agentType must be a number or string")
	}

	// Try to parse string as number
	if num, err := strconv.Atoi(str); err == nil {
		*a = AgentType(num)
		return nil
	}

	// Try to match string name
	switch str {
	case "servicenowresponse", "servicenow", "ServiceNowResponse", "ServiceNow":
		*a = AgentTypeServiceNowResponse
	case "custom", "Custom":
		*a = AgentTypeCustom
	default:
		return fmt.Errorf("unknown agentType: %s (valid values: 0, 1, 'servicenowresponse', 'custom')", str)
	}

	return nil
}

// MarshalJSON implements custom JSON marshaling for AgentType
func (a AgentType) MarshalJSON() ([]byte, error) {
	return json.Marshal(int(a))
}

// FlexibleInt64 is a custom type that can unmarshal from both int64 and string
type FlexibleInt64 int64

// UnmarshalJSON implements custom JSON unmarshaling for FlexibleInt64
// It accepts both numeric values and string values
func (f *FlexibleInt64) UnmarshalJSON(data []byte) error {
	// Try to unmarshal as number first
	var num int64
	if err := json.Unmarshal(data, &num); err == nil {
		*f = FlexibleInt64(num)
		return nil
	}

	// Try to unmarshal as string
	var str string
	if err := json.Unmarshal(data, &str); err != nil {
		return fmt.Errorf("timestamp must be a number or string")
	}

	// Try to parse string as number
	num, err := strconv.ParseInt(str, 10, 64)
	if err != nil {
		return fmt.Errorf("invalid timestamp format: %s (must be a valid number)", str)
	}

	*f = FlexibleInt64(num)
	return nil
}

// MarshalJSON implements custom JSON marshaling for FlexibleInt64
func (f FlexibleInt64) MarshalJSON() ([]byte, error) {
	return json.Marshal(int64(f))
}

// FlexibleFloat64 is a custom type that can unmarshal from both float64 and string
type FlexibleFloat64 float64

// UnmarshalJSON implements custom JSON unmarshaling for FlexibleFloat64
// It accepts both numeric values and string values
func (f *FlexibleFloat64) UnmarshalJSON(data []byte) error {
	// Try to unmarshal as number first
	var num float64
	if err := json.Unmarshal(data, &num); err == nil {
		*f = FlexibleFloat64(num)
		return nil
	}

	// Try to unmarshal as string
	var str string
	if err := json.Unmarshal(data, &str); err != nil {
		return fmt.Errorf("value must be a number or string")
	}

	// Try to parse string as number
	num, err := strconv.ParseFloat(str, 64)
	if err != nil {
		return fmt.Errorf("invalid value format: %s (must be a valid number)", str)
	}

	*f = FlexibleFloat64(num)
	return nil
}

// MarshalJSON implements custom JSON marshaling for FlexibleFloat64
func (f FlexibleFloat64) MarshalJSON() ([]byte, error) {
	return json.Marshal(float64(f))
}

// MetricItem represents a single metric with name and value
type MetricItem struct {
	Name       string          `json:"name,omitempty"`
	Value      FlexibleFloat64 `json:"value"`
	MetricName string          `json:"metricName,omitempty"` // Support Java field name
}

// GetName returns the metric name, checking both 'name' and 'metricName' fields
func (m *MetricItem) GetName() string {
	if m.Name != "" {
		return m.Name
	}
	return m.MetricName
}

// IncomingData represents the data format received from external agents
type IncomingData struct {
	Environment                string        `json:"environment"` // staging, production, nbc, etc.
	Timestamp                  FlexibleInt64 `json:"timestamp"`   // 13-digit epoch (ms)
	AgentType                  AgentType     `json:"agentType"`   // 0 = servicenowresponse, 1 = custom
	MetricList                 []MetricItem  `json:"metriclist,omitempty"`
	MetricPerformanceStatsList []MetricItem  `json:"metricPerformanceStatsList,omitempty"` // Support Java field name
}

// GetMetrics returns the metrics list, checking both field names
func (d *IncomingData) GetMetrics() []MetricItem {
	if len(d.MetricList) > 0 {
		return d.MetricList
	}
	return d.MetricPerformanceStatsList
}

// APIResponse represents the standard API response
type APIResponse struct {
	Success bool        `json:"success"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// HealthCheckResponse represents the health check response
type HealthCheckResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
	Uptime  string `json:"uptime"`
}
