package models

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// ParseDuration parses duration strings like "5m", "1h", "30s" into time.Duration
func ParseDuration(s string) (time.Duration, error) {
	if s == "now" || s == "" {
		return 0, nil
	}

	// Handle relative time strings
	if strings.HasSuffix(s, "m") {
		minutes, err := strconv.Atoi(strings.TrimSuffix(s, "m"))
		if err != nil {
			return 0, fmt.Errorf("invalid duration format: %s", s)
		}
		return time.Duration(minutes) * time.Minute, nil
	}

	if strings.HasSuffix(s, "h") {
		hours, err := strconv.Atoi(strings.TrimSuffix(s, "h"))
		if err != nil {
			return 0, fmt.Errorf("invalid duration format: %s", s)
		}
		return time.Duration(hours) * time.Hour, nil
	}

	if strings.HasSuffix(s, "s") {
		seconds, err := strconv.Atoi(strings.TrimSuffix(s, "s"))
		if err != nil {
			return 0, fmt.Errorf("invalid duration format: %s", s)
		}
		return time.Duration(seconds) * time.Second, nil
	}

	if strings.HasSuffix(s, "d") {
		days, err := strconv.Atoi(strings.TrimSuffix(s, "d"))
		if err != nil {
			return 0, fmt.Errorf("invalid duration format: %s", s)
		}
		return time.Duration(days) * 24 * time.Hour, nil
	}

	// Try parsing as standard Go duration
	return time.ParseDuration(s)
}

// GetQueryTimeRange calculates start and end times for a query
func GetQueryTimeRange(startTime, endTime string, lastQueryTime *time.Time) (time.Time, time.Time, error) {
	now := time.Now()

	var start, end time.Time

	// Handle end time
	if endTime == "now" || endTime == "" {
		end = now
	} else {
		endDuration, err := ParseDuration(endTime)
		if err != nil {
			return start, end, fmt.Errorf("invalid end time: %v", err)
		}
		end = now.Add(-endDuration)
	}

	// Handle start time
	if startTime == "now" {
		start = now
	} else {
		startDuration, err := ParseDuration(startTime)
		if err != nil {
			return start, end, fmt.Errorf("invalid start time: %v", err)
		}
		start = now.Add(-startDuration)
	}

	// If we have a last query time, use it as start time to avoid duplicates
	if lastQueryTime != nil && !lastQueryTime.IsZero() {
		if lastQueryTime.After(start) {
			start = *lastQueryTime
		}
	}

	// Ensure start is before end
	if start.After(end) {
		start, end = end, start
	}

	return start, end, nil
}

// FormatTimeForLoki formats time for Loki API (RFC3339)
func FormatTimeForLoki(t time.Time) string {
	return t.Format(time.RFC3339Nano)
}

// ParseLokiTimestamp parses Loki timestamp (nanoseconds since epoch)
func ParseLokiTimestamp(ts string) (time.Time, error) {
	nsec, err := strconv.ParseInt(ts, 10, 64)
	if err != nil {
		return time.Time{}, fmt.Errorf("invalid timestamp: %s", ts)
	}
	return time.Unix(0, nsec), nil
}

// ConvertToUnixMillis converts time.Time to Unix milliseconds
func ConvertToUnixMillis(t time.Time) int64 {
	return t.UnixNano() / int64(time.Millisecond)
}

// SanitizeLogMessage cleans up log message for InsightFinder
func SanitizeLogMessage(message string) string {
	// Remove null characters and other control characters
	message = strings.ReplaceAll(message, "\x00", "")
	message = strings.ReplaceAll(message, "\r", "")

	// Trim whitespace
	message = strings.TrimSpace(message)

	return message
}

// ExtractContainerName extracts container name from labels
func ExtractContainerName(labels map[string]string) string {
	if container, ok := labels["container"]; ok && container != "" {
		return container
	}
	if pod, ok := labels["pod"]; ok && pod != "" {
		return pod
	}
	if job, ok := labels["job"]; ok && job != "" {
		return job
	}
	if app, ok := labels["app"]; ok && app != "" {
		return app
	}
	return "unknown"
}

// MergeLabels merges additional labels with existing ones
func MergeLabels(existing, additional map[string]string) map[string]string {
	result := make(map[string]string)

	// Copy existing labels
	for k, v := range existing {
		result[k] = v
	}

	// Add additional labels (overwrites existing if same key)
	for k, v := range additional {
		result[k] = v
	}

	return result
}

// ValidateLogEntry checks if a log entry is valid
func ValidateLogEntry(entry LogEntry) bool {
	if entry.Timestamp.IsZero() {
		return false
	}
	if entry.Message == "" {
		return false
	}
	return true
}

// IsEmptyLogMessage checks if a log message is effectively empty
func IsEmptyLogMessage(message string) bool {
	cleaned := strings.TrimSpace(message)
	cleaned = strings.ReplaceAll(cleaned, "\n", "")
	cleaned = strings.ReplaceAll(cleaned, " ", "")
	return cleaned == ""
}
