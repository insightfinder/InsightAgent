package netexperience

import (
	"net/http"
	"sync"
	"time"

	config "github.com/insightfinder/netexperience-agent/configs"
	"github.com/insightfinder/netexperience-agent/pkg/models"
)

// Service handles NetExperience API interactions
type Service struct {
	config     config.NetExperienceConfig
	httpClient *http.Client

	// Authentication
	accessToken  string
	refreshToken string
	tokenExpiry  time.Time
	tokenMutex   sync.RWMutex

	// Rate limiting
	rateLimiter *RateLimiter

	// Cache
	cache      *models.CachedData
	cacheMutex sync.RWMutex
}

// TokenResponse represents the authentication response
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
	TokenType    string `json:"token_type"`
}

// LoginRequest represents the login request payload
type LoginRequest struct {
	UserID   string `json:"userId"`
	Password string `json:"password"`
}

// RefreshRequest represents the token refresh request payload
type RefreshRequest struct {
	UserID       string `json:"userId"`
	Password     string `json:"password"`
	RefreshToken string `json:"refreshToken"`
}

// RateLimiter implements token bucket rate limiting
type RateLimiter struct {
	tokens     int
	maxTokens  int
	refillRate time.Duration
	lastRefill time.Time
	mu         sync.Mutex
}
