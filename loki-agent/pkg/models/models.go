package models

import (
	"time"
)

// LogEntry represents a single log entry from Loki
type LogEntry struct {
	Timestamp time.Time         `json:"timestamp"`
	Message   string            `json:"message"`
	Labels    map[string]string `json:"labels"`
	Stream    StreamInfo        `json:"stream"`
}

// StreamInfo contains metadata about the log stream
type StreamInfo struct {
	Namespace string `json:"namespace,omitempty"`
	Pod       string `json:"pod,omitempty"`
	Container string `json:"container,omitempty"`
	Node      string `json:"node,omitempty"`
	App       string `json:"app,omitempty"`
	Job       string `json:"job,omitempty"`
	Instance  string `json:"instance,omitempty"`
	Filename  string `json:"filename,omitempty"`
}

// QueryResult represents the result of a Loki query
type QueryResult struct {
	QueryName string     `json:"query_name"`
	Query     string     `json:"query"`
	Entries   []LogEntry `json:"entries"`
	Stats     QueryStats `json:"stats"`
	Timestamp time.Time  `json:"timestamp"`
}

// QueryStats contains statistics about query execution
type QueryStats struct {
	TotalEntriesReturned    int     `json:"total_entries_returned"`
	TotalLinesProcessed     int     `json:"total_lines_processed"`
	TotalBytesProcessed     int     `json:"total_bytes_processed"`
	ExecutionTime           float64 `json:"execution_time"`
	QueueTime               float64 `json:"queue_time"`
	Subqueries              int     `json:"subqueries"`
	BytesProcessedPerSecond int     `json:"bytes_processed_per_second"`
	LinesProcessedPerSecond int     `json:"lines_processed_per_second"`
}

// LokiResponse represents the complete response from Loki API
type LokiResponse struct {
	Status string `json:"status"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Stream map[string]string `json:"stream"`
			Values [][]string        `json:"values"`
		} `json:"result"`
		Stats struct {
			Summary struct {
				BytesProcessedPerSecond int     `json:"bytesProcessedPerSecond"`
				LinesProcessedPerSecond int     `json:"linesProcessedPerSecond"`
				TotalBytesProcessed     int     `json:"totalBytesProcessed"`
				TotalLinesProcessed     int     `json:"totalLinesProcessed"`
				ExecTime                float64 `json:"execTime"`
				QueueTime               float64 `json:"queueTime"`
				Subqueries              int     `json:"subqueries"`
				TotalEntriesReturned    int     `json:"totalEntriesReturned"`
			} `json:"summary"`
		} `json:"stats"`
	} `json:"data"`
}

// ProcessedLogData represents data ready for InsightFinder
type ProcessedLogData struct {
	Timestamp int64       `json:"timestamp"` // Unix timestamp in milliseconds
	Tag       string      `json:"tag"`       // Instance/container identifier
	Data      interface{} `json:"data"`      // Log message or structured data
}

// CollectionStats tracks agent performance metrics
type CollectionStats struct {
	TotalQueries        int           `json:"total_queries"`
	TotalLogEntries     int           `json:"total_log_entries"`
	ProcessedEntries    int           `json:"processed_entries"`
	ErrorCount          int           `json:"error_count"`
	StartTime           time.Time     `json:"start_time"`
	LastUpdateTime      time.Time     `json:"last_update_time"`
	AverageQueryTime    time.Duration `json:"average_query_time"`
	LastSuccessfulQuery time.Time     `json:"last_successful_query"`
	QueriesPerMinute    float64       `json:"queries_per_minute"`
}
