package ruckus

import (
	"net/http"
	"sync"
	"time"

	config "github.com/insightfinder/ruckus-agent/configs"
)

type Service struct {
	config        config.RuckusConfig
	httpClient    *http.Client
	baseURL       string
	sessionMutex  sync.RWMutex
	lastAuthTime  time.Time
	sessionExpiry time.Duration
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
