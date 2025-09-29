package models

import (
	"regexp"
	"strings"
)

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