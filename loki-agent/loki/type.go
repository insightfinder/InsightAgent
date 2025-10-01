package loki

import (
	"time"
)

// Service represents the Loki service client
type Service struct {
	BaseURL               string
	Username              string
	Password              string
	VerifySSL             bool
	MaxConcurrentRequests int
	MaxRetries            int
	QueryTimeout          time.Duration

	// Internal client state
	httpClient      interface{} // Will be *http.Client
	isHealthy       bool
	lastHealthCheck time.Time
}

// QueryRequest represents a query request to Loki
type QueryRequest struct {
	Query     string            `json:"query"`
	Start     time.Time         `json:"start"`
	End       time.Time         `json:"end"`
	Limit     int               `json:"limit"`
	Direction string            `json:"direction"` // "forward" or "backward"
	Step      string            `json:"step,omitempty"`
	Labels    map[string]string `json:"labels,omitempty"`
}

// HealthCheckResponse represents Loki health check response
type HealthCheckResponse struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

// LabelResponse represents response from Loki labels API
type LabelResponse struct {
	Status string   `json:"status"`
	Data   []string `json:"data"`
}

// LabelValuesResponse represents response from Loki label values API
type LabelValuesResponse struct {
	Status string   `json:"status"`
	Data   []string `json:"data"`
}

// SeriesResponse represents response from Loki series API
type SeriesResponse struct {
	Status string              `json:"status"`
	Data   []map[string]string `json:"data"`
}
