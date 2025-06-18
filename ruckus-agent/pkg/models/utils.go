package models

import (
	"encoding/json"
	"os"
	"regexp"
	"strings"

	"github.com/sirupsen/logrus"
)

// cleanDeviceName cleans and formats the device name according to specific rules
func cleanDeviceName(deviceName string) string {
	if deviceName == "" {
		return deviceName
	}

	// Strip underscores and replace with dots
	deviceName = strings.ReplaceAll(deviceName, "_", ".")

	// Replace colons with hyphens
	deviceName = strings.ReplaceAll(deviceName, ":", "-")

	// Regex to match leading special characters (hyphens, underscores, etc.)
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

// ----------------- Left for future use: This function can be used to generate a component name based on the instance name. ---------------
// generateComponentNameFromInstanceName generates a component name based on the instance name
// func generateComponentNameFromInstanceName(instanceName string) string {
// result := instanceName
// lowerInstanceName := strings.ToLower(instanceName)

// if strings.Contains(lowerInstanceName, "ap") {
// 	result = "AP"
// } else if strings.Contains(lowerInstanceName, "he-swt") || strings.Contains(lowerInstanceName, "he-sw") {
// 	result = "HE-SW"
// } else if strings.Contains(lowerInstanceName, "swt") || strings.Contains(lowerInstanceName, "sw") || strings.Contains(lowerInstanceName, "switch") {
// 	result = "Switch"
// } else if strings.Contains(lowerInstanceName, "enb") {
// 	result = "eNB"
// } else if strings.Contains(lowerInstanceName, "isp") {
// 	result = "ISP"
// } else if strings.Contains(lowerInstanceName, "mikrotik") || strings.Contains(lowerInstanceName, "microtik") {
// 	result = "Mikrotik"
// } else if strings.Contains(lowerInstanceName, "esxi") {
// 	result = "ESXi"
// } else if strings.Contains(lowerInstanceName, "pdu") {
// 	result = "PDU"
// } else if strings.Contains(lowerInstanceName, "ups") {
// 	result = "UPS"
// } else if strings.Contains(lowerInstanceName, "cpe") {
// 	result = "CPE"
// } else if strings.Contains(lowerInstanceName, "smartbox") {
// 	result = "Smartbox"
// } else if strings.Contains(lowerInstanceName, "wan") {
// 	result = "WAN"
// } else if strings.Contains(lowerInstanceName, "router") {
// 	result = "Router"
// } else if strings.Contains(lowerInstanceName, "ptp") {
// 	result = "PTP"
// } else if strings.Contains(lowerInstanceName, "olt") {
// 	result = "OLT"
// }

// if result == instanceName {
// 	fmt.Printf("Unable to generate component name for instance: %s\n", instanceName)
// }

// return result
// }

func ProcessZoneMappings(metricData []MetricData) []MetricData {
	zoneMappingFile := "pkg/models/mapping.json"

	// Read zone mapping data
	zoneMappingData, err := os.ReadFile(zoneMappingFile)
	if err != nil {
		logrus.Warn("Failed to read zone mapping file:", err)
		return metricData // Return original data if zone mapping file cannot be read
	}

	var instanceZoneMap map[string]string
	err = json.Unmarshal(zoneMappingData, &instanceZoneMap)
	if err != nil {
		logrus.Warn("Failed to parse zone mapping JSON:", err)
		return metricData // Return original data if zone mapping JSON cannot be parsed
	}

	for i := range metricData {
		zoneName, exists := instanceZoneMap[metricData[i].Zone]

		if exists && zoneName != "" {
			metricData[i].Zone = zoneName
		}
	}

	return metricData
}
