package positron

import (
	"time"

	"github.com/insightfinder/positron-agent/pkg/models"
)

// Convert Endpoint to MetricData
func (e *Endpoint) ToMetricData() *models.MetricData {
	cleanName := models.CleanDeviceName(e.ConfEndpointName)

	// Use current Unix timestamp in seconds, will be converted to ms later
	currentTime := time.Now().Unix()

	metric := &models.MetricData{
		Timestamp:     currentTime,
		InstanceName:  cleanName,
		ComponentName: "Endpoint",
		Data: map[string]interface{}{
			// Format metric names using safe formatting
			models.MakeSafeDataKey("DS PHY rate"): e.RxPhyRate,
			models.MakeSafeDataKey("US PHY rate"): e.TxPhyRate,
			models.MakeSafeDataKey("DS Max BW"):   e.RxMaxXput,
			models.MakeSafeDataKey("US Max BW"):   e.TxMaxXput,
		},
	}

	return metric
}

// Convert Device to MetricData
func (d *Device) ToMetricData() *models.MetricData {
	cleanName := models.CleanDeviceName(d.Name)

	// Use current Unix timestamp in seconds, will be converted to ms later
	currentTime := time.Now().Unix()

	metric := &models.MetricData{
		Timestamp:     currentTime,
		InstanceName:  cleanName,
		ComponentName: "Device",
		Data: map[string]interface{}{
			// Format metric names using safe formatting - Capacity Metrics
			models.MakeSafeDataKey("Ports"):       d.Ports,
			models.MakeSafeDataKey("Endpoints"):   d.Endpoints,
			models.MakeSafeDataKey("Subscribers"): d.Subscribers,
			models.MakeSafeDataKey("Bandwidths"):  d.Bandwidths,
		},
		IP: d.IPAddress,
	}

	return metric
}

// Convert Alarm to LogData
func (a *Alarm) ToLogData() map[string]interface{} {
	// Use current Unix timestamp in milliseconds for logs
	currentTimeMs := time.Now().Unix() * 1000

	// Build a comprehensive data object to include all alarm details under "data"
	data := map[string]interface{}{
		// A human-readable message
		"message": a.Description + ": " + a.Condition,
		// Core alarm fields
		"system_name":          a.SystemName,
		"product_class":        a.ProductClass,
		"severity":             a.Severity,
		"condition":            a.Condition,
		"service_affecting":    a.ServiceAffecting,
		"description":          a.Description,
		"occurred":             a.Occurred,
		"device_serial_number": a.DeviceSerialNumber,
		"received":             a.Received,
		"cleared":              a.Cleared,
		"details":              a.Details,
	}

	return map[string]interface{}{
		"timestamp":     currentTimeMs,
		"tag":           models.CleanDeviceName(a.SystemName),
		// "componentName": models.CleanDeviceName(a.SystemName),
		"data":          data,
	}
}

// // Utility functions
// func boolToInt(b bool) int {
// 	if b {
// 		return 1
// 	}
// 	return 0
// }

// // parseUptime tries to parse uptime string to seconds
// // Supports formats like "11 days, 15h 43m 24s" or "0 days, 0h 14m 48s" or "12d 09:09:08"
// func parseUptime(uptime string) int64 {
// 	// Try format: "11 days, 15h 43m 24s"
// 	re1 := regexp.MustCompile(`(\d+)\s+days?,\s*(\d+)h\s*(\d+)m\s*(\d+)s`)
// 	if matches := re1.FindStringSubmatch(uptime); len(matches) == 5 {
// 		days, _ := strconv.Atoi(matches[1])
// 		hours, _ := strconv.Atoi(matches[2])
// 		minutes, _ := strconv.Atoi(matches[3])
// 		seconds, _ := strconv.Atoi(matches[4])

// 		return int64(days*24*3600 + hours*3600 + minutes*60 + seconds)
// 	}

// 	// Try format: "12d 09:09:08"
// 	re2 := regexp.MustCompile(`(\d+)d\s+(\d+):(\d+):(\d+)`)
// 	if matches := re2.FindStringSubmatch(uptime); len(matches) == 5 {
// 		days, _ := strconv.Atoi(matches[1])
// 		hours, _ := strconv.Atoi(matches[2])
// 		minutes, _ := strconv.Atoi(matches[3])
// 		seconds, _ := strconv.Atoi(matches[4])

// 		return int64(days*24*3600 + hours*3600 + minutes*60 + seconds)
// 	}

// 	return 0 // Could not parse
// }
