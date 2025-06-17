package models

import (
	"regexp"
	"strings"
)

// cleanDeviceNamePrefix removes common prefix patterns from device names
func cleanDeviceNamePrefix(deviceName string) string {
	if deviceName == "" {
		return deviceName
	}

	// Regex to match leading dashes, underscores, or other common prefixes
	re := regexp.MustCompile(`^[-_\s]+`)
	cleaned := re.ReplaceAllString(deviceName, "")

	// Trim any remaining whitespace
	cleaned = strings.TrimSpace(cleaned)

	// If the cleaned name is empty, return the original
	if cleaned == "" {
		return deviceName
	}

	return cleaned
}
