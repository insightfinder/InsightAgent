package ruckus

import (
	"net/http"
	"sync"
	"time"

	config "github.com/insightfinder/ruckus-agent/configs"
)

type Service struct {
	Config        config.RuckusConfig
	HttpClient    *http.Client
	BaseURL       string
	SessionExpiry time.Duration
	LastAuthTime  time.Time
	SessionMutex  sync.RWMutex
	// MaxConcurrentRequests int
	// RequestSemaphore chan struct{}
}

// Error response structure for API errors
type ErrorResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// Authentication response structure
type AuthResponse struct {
	ControllerVersion string `json:"controllerVersion"`
}

// Simplified structures for bulk query with pagination
type APBulkQueryRequest struct {
	Filters []Filter `json:"filters"`
	Page    int      `json:"page"`
	Limit   int      `json:"limit"`
}

type Filter struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}
