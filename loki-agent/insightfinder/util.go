package insightfinder

import (
	"math"
	"regexp"
	"strconv"
	"strings"
)

// Helper function to convert any numeric value to float64
func convertToFloat64(value interface{}) (float64, bool) {
	switch v := value.(type) {
	case float64:
		// Convert negative values to positive (matching Python behavior)
		if v < 0 {
			return math.Abs(v), true
		}
		return v, true
	case float32:
		result := float64(v)
		if result < 0 {
			return math.Abs(result), true
		}
		return result, true
	case int:
		result := float64(v)
		if result < 0 {
			return math.Abs(result), true
		}
		return result, true
	case int8:
		result := float64(v)
		if result < 0 {
			return math.Abs(result), true
		}
		return result, true
	case int16:
		result := float64(v)
		if result < 0 {
			return math.Abs(result), true
		}
		return result, true
	case int32:
		result := float64(v)
		if result < 0 {
			return math.Abs(result), true
		}
		return result, true
	case int64:
		result := float64(v)
		if result < 0 {
			return math.Abs(result), true
		}
		return result, true
	case uint:
		return float64(v), true
	case uint8:
		return float64(v), true
	case uint16:
		return float64(v), true
	case uint32:
		return float64(v), true
	case uint64:
		return float64(v), true
	case bool:
		if v {
			return 1.0, true
		}
		return 0.0, true
	case string:
		if parsedFloat, err := strconv.ParseFloat(v, 64); err == nil {
			// Convert negative values to positive (matching Python behavior)
			if parsedFloat < 0 {
				return math.Abs(parsedFloat), true
			}
			return parsedFloat, true
		}
		return 0, false
	default:
		return 0, false
	}
}

// alignTimestamp aligns timestamp to sampling interval (matching Python function)
func alignTimestamp(timestamp int64, samplingInterval int) int64 {
	if samplingInterval == 0 || timestamp == 0 {
		return timestamp
	}
	samplingIntervalMs := int64(samplingInterval * 1000)
	return (timestamp / samplingIntervalMs) * samplingIntervalMs
}

// CleanDeviceName cleans and formats the device name according to specific rules
func CleanDeviceName(deviceName string) string {
	if deviceName == "" {
		return deviceName
	}

	// Strip underscores and replace with dots
	deviceName = strings.ReplaceAll(deviceName, "_", ".")

	// Replace colons with hyphens
	deviceName = strings.ReplaceAll(deviceName, ":", "-")

	// Replace slashes with periods
	deviceName = strings.ReplaceAll(deviceName, "/", ".")

	// Remove leading special characters (hyphens, underscores, etc.) - matching Python
	re := regexp.MustCompile(`^[-_\W]+`)
	cleaned := re.ReplaceAllString(deviceName, "")

	// Trim any remaining whitespace
	cleaned = strings.TrimSpace(cleaned)

	// If the cleaned name is empty, return the original
	if cleaned == "" {
		return deviceName
	}

	return cleaned
}

// MakeSafeDataKey formats metric names to be safe
func MakeSafeDataKey(metric string) string {
	// Left brace to parenthesis
	metric = strings.ReplaceAll(metric, "[", "(")
	// Right brace to parenthesis
	metric = strings.ReplaceAll(metric, "]", ")")
	// Period to forward slash
	metric = strings.ReplaceAll(metric, ".", "/")
	// Underscore to hyphen
	metric = strings.ReplaceAll(metric, "_", "-")
	// Colon to hyphen
	metric = strings.ReplaceAll(metric, ":", "-")
	// Comma to hyphen
	metric = strings.ReplaceAll(metric, ",", "-")
	return metric
}
