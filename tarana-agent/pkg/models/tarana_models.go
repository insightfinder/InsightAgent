package models

import (
	"math"
	"strings"
	"time"
)

// TaranaMetric represents a metric collected from Tarana API
type TaranaMetric struct {
	DeviceID      string
	HostName      string
	IP            string
	DeviceType    string
	MetricName    string
	MetricValue   float64
	Timestamp     int64
	InstanceName  string
	ComponentName string
}

// TaranaLog represents a log/alarm entry from Tarana API
type TaranaLog struct {
	DeviceID      string
	HostName      string
	IP            string
	DeviceType    string
	AlarmID       string
	AlarmText     string
	Status        string
	Severity      int
	Category      string
	Timestamp     int64
	TimeCreated   int64
	TimeCleared   int64
	InstanceName  string
	ComponentName string
	DisplayID     string
}

// ConvertDeviceMetricsToIFMetrics converts Tarana device metrics to InsightFinder format
func ConvertDeviceMetricsToIFMetrics(deviceMetrics TaranaDeviceMetrics, device TaranaDevice, kpiMapping map[string]string) []TaranaMetric {
	var metrics []TaranaMetric

	instanceName := device.HostName
	componentName := device.Type
	currentTime := time.Now().Unix()

	// Only process KPIs that are actually present in the API response
	for _, kpi := range deviceMetrics.KPIs {
		// Skip invalid or empty KPIs
		if kpi.KPI == "" {
			continue
		}

		// Get metric name from configuration mapping, fallback to cleaned name
		metricName, exists := kpiMapping[kpi.KPI]
		if !exists {
			metricName = cleanMetricName(kpi.KPI)
		}

		// Convert negative values to positive since InsightFinder only supports positive metrics
		metricValue := kpi.Value
		if metricValue < 0 {
			metricValue = math.Abs(metricValue)
		}

		metric := TaranaMetric{
			DeviceID:      deviceMetrics.DeviceID,
			HostName:      device.HostName,
			IP:            device.IP,
			DeviceType:    device.Type,
			MetricName:    metricName,
			MetricValue:   metricValue,
			Timestamp:     currentTime,
			InstanceName:  instanceName,
			ComponentName: componentName,
		}

		metrics = append(metrics, metric)
	}

	return metrics
}

// ConvertAlarmToIFLog converts Tarana alarm to InsightFinder log format
func ConvertAlarmToIFLog(alarm TaranaAlarmDetail) TaranaLog {
	instanceName := CleanDeviceName(alarm.DeviceHostName)
	if instanceName == "" {
		instanceName = CleanDeviceName(alarm.DeviceSerialNumber)
	}

	componentName := alarm.RadioType
	currentTime := time.Now().Unix()

	return TaranaLog{
		DeviceID:      alarm.DeviceSerialNumber,
		HostName:      alarm.DeviceHostName,
		IP:            alarm.DeviceIP,
		DeviceType:    alarm.RadioType,
		AlarmID:       alarm.ID,
		AlarmText:     alarm.Text,
		Status:        alarm.Status,
		Severity:      alarm.Severity,
		Category:      alarm.Category,
		Timestamp:     currentTime,
		TimeCreated:   alarm.TimeCreated,
		TimeCleared:   alarm.TimeCleared,
		InstanceName:  instanceName,
		ComponentName: componentName,
		DisplayID:     alarm.DisplayID,
	}
}

// ToInsightFinderMetric converts TaranaMetric to InsightFinder metric format
func (tm *TaranaMetric) ToInsightFinderMetric() MetricData {
	data := make(map[string]interface{})
	data[tm.MetricName] = tm.MetricValue

	return MetricData{
		InstanceName:  tm.InstanceName,
		ComponentName: tm.ComponentName,
		Data:          data,
		Timestamp:     tm.Timestamp,
		IP:            tm.IP,
	}
}

// ToInsightFinderLog converts TaranaLog to InsightFinder log format as JSON object
func (tl *TaranaLog) ToInsightFinderLog() map[string]interface{} {
	// Use current Unix timestamp in milliseconds for logs
	currentTimeMs := time.Now().Unix() * 1000

	// Build comprehensive data object with all alarm details
	data := map[string]interface{}{
		// Human-readable message
		"message": tl.AlarmText,
		// Core alarm fields
		"alarm_id":        tl.AlarmID,
		"status":          tl.Status,
		"severity":        tl.Severity,
		"category":        tl.Category,
		"device_id":       tl.DeviceID,
		"device_hostname": tl.HostName,
		"device_ip":       tl.IP,
		"device_type":     tl.DeviceType,
		"time_created":    tl.TimeCreated,
		"time_cleared":    tl.TimeCleared,
		"instance_name":   tl.InstanceName,
		"component_name":  tl.ComponentName,
		"display_id":      tl.DisplayID,
	}

	return map[string]interface{}{
		"timestamp":     currentTimeMs,
		"tag":           tl.HostName,
		"componentName": tl.ComponentName,
		"instanceName":  tl.InstanceName,
		"data":          data,
		"ipAddress":     tl.IP,
	}
}

// cleanMetricName extracts the last part of the KPI path and converts to uppercase
// Examples:
//
//	"/connections/connection/state/dl-snr" -> "DL-SNR"
//	"/connections/connection/state/rf-range" -> "RF-RANGE"
//	"/connections/connection/radios/radio[id=0]/state/rx-signal-level/min" -> "MIN"
func cleanMetricName(kpi string) string {
	// Split by "/" and take the last part
	parts := strings.Split(kpi, "/")
	if len(parts) == 0 {
		return strings.ToUpper(kpi)
	}

	lastPart := parts[len(parts)-1]

	// Clean up any remaining special characters and convert to uppercase
	metricName := strings.ReplaceAll(lastPart, "[", "_")
	metricName = strings.ReplaceAll(metricName, "]", "")
	metricName = strings.ReplaceAll(metricName, "=", "_")

	// Convert to uppercase
	metricName = strings.ToUpper(metricName)

	return metricName
}

// BatchTaranaMetrics groups TaranaMetrics for batch processing
func BatchTaranaMetrics(metrics []TaranaMetric, batchSize int) [][]TaranaMetric {
	var batches [][]TaranaMetric

	for i := 0; i < len(metrics); i += batchSize {
		end := i + batchSize
		if end > len(metrics) {
			end = len(metrics)
		}
		batches = append(batches, metrics[i:end])
	}

	return batches
}

// BatchTaranaLogs groups TaranaLogs for batch processing
func BatchTaranaLogs(logs []TaranaLog, batchSize int) [][]TaranaLog {
	var batches [][]TaranaLog

	for i := 0; i < len(logs); i += batchSize {
		end := i + batchSize
		if end > len(logs) {
			end = len(logs)
		}
		batches = append(batches, logs[i:end])
	}

	return batches
}

// ConvertToMetricDataArray converts slice of TaranaMetrics to MetricData array
func ConvertToMetricDataArray(taranaMetrics []TaranaMetric) []MetricData {
	metrics := make([]MetricData, len(taranaMetrics))
	for i, tm := range taranaMetrics {
		metrics[i] = tm.ToInsightFinderMetric()
	}
	return metrics
}

// ConvertToLogDataArray converts slice of TaranaLogs to JSON object array (like positron)
func ConvertToLogDataArray(taranaLogs []TaranaLog) []map[string]interface{} {
	logs := make([]map[string]interface{}, len(taranaLogs))
	for i, tl := range taranaLogs {
		logs[i] = tl.ToInsightFinderLog()
	}
	return logs
}

// DeviceInfo stores device mapping information
type DeviceInfo struct {
	SerialNumber string
	HostName     string
	IP           string
	Type         string
}

// CreateDeviceMapping creates a map of serial number to device info
func CreateDeviceMapping(devices []TaranaDevice) map[string]DeviceInfo {
	deviceMap := make(map[string]DeviceInfo)

	for _, device := range devices {
		deviceMap[device.SerialNumber] = DeviceInfo{
			SerialNumber: device.SerialNumber,
			HostName:     device.HostName,
			IP:           device.IP,
			Type:         device.Type,
		}
	}

	return deviceMap
}
