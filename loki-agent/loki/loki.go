package loki

import (
	"context"
	"crypto/tls"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/carlmjohnson/requests"
	config "github.com/insightfinder/loki-agent/configs"
	"github.com/insightfinder/loki-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

const (
	HEALTH_ENDPOINT       = "/ready"
	CONFIG_ENDPOINT       = "/config"
	QUERY_RANGE_ENDPOINT  = "/loki/api/v1/query_range"
	QUERY_ENDPOINT        = "/loki/api/v1/query"
	LABELS_ENDPOINT       = "/loki/api/v1/labels"
	LABEL_VALUES_ENDPOINT = "/loki/api/v1/label/{name}/values"
	SERIES_ENDPOINT       = "/loki/api/v1/series"
)

// NewService creates a new Loki service instance
func NewService(cfg config.LokiConfig) *Service {
	// Create HTTP client with proper timeout and SSL settings
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: !cfg.VerifySSL},
	}

	client := &http.Client{
		Transport: tr,
		Timeout:   time.Duration(cfg.QueryTimeout) * time.Second,
	}

	service := &Service{
		BaseURL:               cfg.BaseURL,
		Username:              cfg.Username,
		Password:              cfg.Password,
		VerifySSL:             cfg.VerifySSL,
		MaxConcurrentRequests: cfg.MaxConcurrentRequests,
		MaxRetries:            cfg.MaxRetries,
		QueryTimeout:          time.Duration(cfg.QueryTimeout) * time.Second,
		httpClient:            client,
		isHealthy:             false,
		lastHealthCheck:       time.Time{},
	}

	return service
}

// HealthCheck performs a health check against the Loki instance
func (s *Service) HealthCheck() error {
	endpoint := s.BaseURL + HEALTH_ENDPOINT

	var response string
	err := requests.URL(endpoint).
		Client(s.httpClient.(*http.Client)).
		BasicAuth(s.Username, s.Password).
		ToString(&response).
		Fetch(context.Background())

	if err != nil {
		s.isHealthy = false
		return fmt.Errorf("health check failed: %v", err)
	}

	// Loki returns "ready" when healthy
	if !strings.Contains(strings.ToLower(response), "ready") {
		s.isHealthy = false
		return fmt.Errorf("loki not ready: %s", response)
	}

	s.isHealthy = true
	s.lastHealthCheck = time.Now()
	return nil
}

// QueryRange executes a range query against Loki
func (s *Service) QueryRange(req QueryRequest) (*models.LokiResponse, error) {
	endpoint := s.BaseURL + QUERY_RANGE_ENDPOINT

	// Build query parameters
	params := url.Values{}
	params.Set("query", req.Query)
	params.Set("start", models.FormatTimeForLoki(req.Start))
	params.Set("end", models.FormatTimeForLoki(req.End))

	if req.Limit > 0 {
		params.Set("limit", strconv.Itoa(req.Limit))
	}

	if req.Direction != "" {
		params.Set("direction", req.Direction)
	} else {
		params.Set("direction", "forward")
	}

	if req.Step != "" {
		params.Set("step", req.Step)
	}

	var response models.LokiResponse
	err := requests.URL(endpoint).
		Client(s.httpClient.(*http.Client)).
		BasicAuth(s.Username, s.Password).
		Params(params).
		ToJSON(&response).
		Fetch(context.Background())

	if err != nil {
		return nil, fmt.Errorf("query range failed: %v", err)
	}

	if response.Status != "success" {
		return nil, fmt.Errorf("query failed with status: %s", response.Status)
	}

	return &response, nil
}

// Query executes an instant query against Loki
func (s *Service) Query(query string, timestamp time.Time, limit int) (*models.LokiResponse, error) {
	endpoint := s.BaseURL + QUERY_ENDPOINT

	params := url.Values{}
	params.Set("query", query)
	params.Set("time", models.FormatTimeForLoki(timestamp))

	if limit > 0 {
		params.Set("limit", strconv.Itoa(limit))
	}

	var response models.LokiResponse
	err := requests.URL(endpoint).
		Client(s.httpClient.(*http.Client)).
		BasicAuth(s.Username, s.Password).
		Params(params).
		ToJSON(&response).
		Fetch(context.Background())

	if err != nil {
		return nil, fmt.Errorf("instant query failed: %v", err)
	}

	if response.Status != "success" {
		return nil, fmt.Errorf("query failed with status: %s", response.Status)
	}

	return &response, nil
}

// GetLabels retrieves all available labels
func (s *Service) GetLabels(start, end time.Time) ([]string, error) {
	endpoint := s.BaseURL + LABELS_ENDPOINT

	params := url.Values{}
	if !start.IsZero() {
		params.Set("start", models.FormatTimeForLoki(start))
	}
	if !end.IsZero() {
		params.Set("end", models.FormatTimeForLoki(end))
	}

	var response LabelResponse
	err := requests.URL(endpoint).
		Client(s.httpClient.(*http.Client)).
		BasicAuth(s.Username, s.Password).
		Params(params).
		ToJSON(&response).
		Fetch(context.Background())

	if err != nil {
		return nil, fmt.Errorf("get labels failed: %v", err)
	}

	if response.Status != "success" {
		return nil, fmt.Errorf("get labels failed with status: %s", response.Status)
	}

	return response.Data, nil
}

// GetLabelValues retrieves all values for a specific label
func (s *Service) GetLabelValues(labelName string, start, end time.Time) ([]string, error) {
	endpoint := s.BaseURL + strings.Replace(LABEL_VALUES_ENDPOINT, "{name}", labelName, 1)

	params := url.Values{}
	if !start.IsZero() {
		params.Set("start", models.FormatTimeForLoki(start))
	}
	if !end.IsZero() {
		params.Set("end", models.FormatTimeForLoki(end))
	}

	var response LabelValuesResponse
	err := requests.URL(endpoint).
		Client(s.httpClient.(*http.Client)).
		BasicAuth(s.Username, s.Password).
		Params(params).
		ToJSON(&response).
		Fetch(context.Background())

	if err != nil {
		return nil, fmt.Errorf("get label values failed: %v", err)
	}

	if response.Status != "success" {
		return nil, fmt.Errorf("get label values failed with status: %s", response.Status)
	}

	return response.Data, nil
}

// ConvertResponseToLogEntries converts Loki API response to LogEntry slice
func (s *Service) ConvertResponseToLogEntries(response *models.LokiResponse, additionalLabels map[string]string) ([]models.LogEntry, error) {
	var entries []models.LogEntry

	for _, result := range response.Data.Result {
		stream := models.StreamInfo{
			Namespace: result.Stream["namespace"],
			Pod:       result.Stream["pod"],
			Container: result.Stream["container"],
			Node:      result.Stream["node_name"],
			App:       result.Stream["app"],
			Job:       result.Stream["job"],
			Instance:  result.Stream["instance"],
			Filename:  result.Stream["filename"],
		}

		for _, value := range result.Values {
			if len(value) != 2 {
				continue // Skip invalid entries
			}

			// Parse timestamp
			timestamp, err := models.ParseLokiTimestamp(value[0])
			if err != nil {
				continue // Skip entries with invalid timestamps
			}

			// Get log message
			message := models.SanitizeLogMessage(value[1])
			if models.IsEmptyLogMessage(message) {
				continue // Skip empty messages
			}

			// Merge labels
			labels := models.MergeLabels(result.Stream, additionalLabels)

			entry := models.LogEntry{
				Timestamp: timestamp,
				Message:   message,
				Labels:    labels,
				Stream:    stream,
			}

			if models.ValidateLogEntry(entry) {
				entries = append(entries, entry)
			}
		}
	}

	// Process Java exceptions by combining multi-line stack traces
	processedEntries := s.ProcessJavaExceptions(entries)

	return processedEntries, nil
}

// IsHealthy returns the current health status
func (s *Service) IsHealthy() bool {
	return s.isHealthy
}

// GetLastHealthCheck returns the timestamp of the last health check
func (s *Service) GetLastHealthCheck() time.Time {
	return s.lastHealthCheck
}

// ProcessJavaExceptions processes Java exception stack traces by combining multi-line entries
func (s *Service) ProcessJavaExceptions(entries []models.LogEntry) []models.LogEntry {
	if len(entries) == 0 {
		return entries
	}

	logrus.Debugf("Processing Java exceptions for %d log entries", len(entries))

	var result []models.LogEntry
	var logCache *models.LogEntry
	exceptionMode := false

	// Add a sentinel entry to ensure last cache is processed
	processEntries := append(entries, models.LogEntry{})

	for i, entry := range processEntries {
		if logCache == nil {
			if i < len(entries) { // Don't cache the sentinel
				logCacheCopy := entry
				logCache = &logCacheCopy
			}
			continue
		}

		// Check if current line is a Java stack trace line and from same pod within time range
		if i < len(entries) && s.isJavaStackTraceLine(entry.Message) &&
			s.isSamePodAndTimeRange(*logCache, entry) {
			// Combine stack trace lines
			logCache.Message += "\n" + entry.Message
			exceptionMode = true
			continue
		} else {
			// Process the cached entry
			if exceptionMode {
				// Add exception entry with combined stack trace
				result = append(result, *logCache)
				exceptionMode = false
			} else {
				// Add normal log entry
				result = append(result, *logCache)
			}

			// Cache the current entry (skip sentinel)
			if i < len(entries) {
				logCacheCopy := entry
				logCache = &logCacheCopy
			} else {
				logCache = nil
			}
		}
	}

	logrus.Debugf("Java exception processing complete: %d entries processed to %d entries", len(entries), len(result))
	return result
}

// isJavaStackTraceLine checks if a log message is part of a Java stack trace
func (s *Service) isJavaStackTraceLine(message string) bool {
	javaStackTraceExceptionRegex := regexp.MustCompile(`Exception:.*`)
	javaStackTraceAtRegex := regexp.MustCompile(`^\s*at.*\(*\)`)
	javaStackTraceCausedByRegex := regexp.MustCompile(`Caused by:`)

	return javaStackTraceAtRegex.MatchString(message) ||
		javaStackTraceCausedByRegex.MatchString(message) ||
		javaStackTraceExceptionRegex.MatchString(message)
}

// isSamePodAndTimeRange checks if two log entries are from the same pod and within 1 second time range
func (s *Service) isSamePodAndTimeRange(cache, current models.LogEntry) bool {
	// Check if same pod
	samePod := cache.Stream.Pod == current.Stream.Pod &&
		cache.Stream.Namespace == current.Stream.Namespace

	// Check if within 1 second time range
	withinTimeRange := current.Timestamp.Sub(cache.Timestamp) <= time.Second*1

	return samePod && withinTimeRange
}
