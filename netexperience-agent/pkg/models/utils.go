package models

import (
	"math"
	"regexp"
	"strings"
)

// CalculateRSSIMetrics calculates RSSI-based metrics
func CalculateRSSIMetrics(rssiValues []int, threshold int) (avg float64, below74, below78, below80 int, percentBelow74, percentBelow78, percentBelow80 float64) {
	if len(rssiValues) == 0 {
		return 0, 0, 0, 0, 0, 0, 0
	}

	sum := 0
	for _, rssi := range rssiValues {
		sum += rssi

		// Count clients below thresholds
		if rssi < -80 {
			below80++
		}
		if rssi < -78 {
			below78++
		}
		if rssi < -74 {
			below74++
		}
	}

	avg = math.Abs(float64(sum) / float64(len(rssiValues)))

	// Calculate percentages only if we have enough clients
	if len(rssiValues) >= threshold {
		percentBelow74 = float64(below74) / float64(len(rssiValues)) * 100
		percentBelow78 = float64(below78) / float64(len(rssiValues)) * 100
		percentBelow80 = float64(below80) / float64(len(rssiValues)) * 100
	}

	return
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
