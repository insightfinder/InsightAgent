package models

// InsightFinder data structure
type MetricData struct {
	Timestamp     int64                  `json:"timestamp"`
	InstanceName  string                 `json:"instanceName"`
	Data          map[string]interface{} `json:"data"`
	Zone          string                 `json:"zone,omitempty"`
	ComponentName string                 `json:"componentName,omitempty"`
	IP            string                 `json:"ip,omitempty"`
}

// EdgeCore specific models
type EdgeCoreMetric struct {
	InstanceName  string  `json:"instanceName"`
	ComponentName string  `json:"componentName"`
	MetricName    string  `json:"metricName"`
	MetricValue   float64 `json:"metricValue"`
	Timestamp     int64   `json:"timestamp"`
	Zone          string  `json:"zone"`
	IPAddress     string  `json:"ipAddress"`
}

// BatchEdgeCoreMetrics splits metrics into batches
func BatchEdgeCoreMetrics(metrics []EdgeCoreMetric, batchSize int) [][]EdgeCoreMetric {
	var batches [][]EdgeCoreMetric
	for i := 0; i < len(metrics); i += batchSize {
		end := i + batchSize
		if end > len(metrics) {
			end = len(metrics)
		}
		batches = append(batches, metrics[i:end])
	}
	return batches
}

// ConvertToMetricDataArray converts EdgeCore metrics to InsightFinder format
func ConvertToMetricDataArray(metrics []EdgeCoreMetric) []MetricData {
	var result []MetricData
	for _, metric := range metrics {
		result = append(result, MetricData{
			Timestamp:     metric.Timestamp,
			InstanceName:  CleanDeviceName(metric.InstanceName),
			ComponentName: metric.ComponentName,
			Zone:          metric.Zone,
			IP:            metric.IPAddress,
			Data: map[string]interface{}{
				metric.MetricName: metric.MetricValue,
			},
		})
	}
	return result
}

// EdgeCore Alarm models - flattened single layer JSON as requested by user
type EdgeCoreAlarm struct {
	// Core alarm identification
	ID           string `json:"id"`
	AlarmCode    string `json:"alarmCode"`
	Severity     string `json:"severity"`
	Acknowledged string `json:"acknowledged"`

	// Timestamps (using milliseconds as strings like in response)
	CreatedTimestamp      string `json:"createdTimestamp"`
	LastModifiedTimestamp string `json:"lastModifiedTimestamp"`

	// Equipment information (flattened from nested structure)
	EquipmentID        string `json:"equipmentId"`
	EquipmentName      string `json:"equipmentName"`
	EquipmentType      string `json:"equipmentType"`
	EquipmentIPAddress string `json:"equipmentIpAddress"`
	LocationName       string `json:"locationName"`

	// Alarm details (flattened)
	Message     string `json:"message"`
	GeneratedBy string `json:"generatedBy"`

	// Organizational information
	CustomerID     string `json:"customerId"`
	CustomerName   string `json:"customerName"`
	LocationID     string `json:"locationId"`
	OriginatorType string `json:"originatorType"`
	ScopeID        string `json:"scopeId"`
	ScopeType      string `json:"scopeType"`

	// InsightFinder specific fields
	Zone          string `json:"zone"`
	ComponentName string `json:"componentName"`
	InstanceName  string `json:"instanceName"`
	Timestamp     int64  `json:"timestamp"`
}

// ConvertAlarmToEdgeCoreLog converts an EdgeCore alarm to InsightFinder log format (matching tarana pattern)
func ConvertAlarmToEdgeCoreLog(alarm EdgeCoreAlarm) map[string]interface{} {
	// Build comprehensive data object with all alarm details
	data := map[string]interface{}{
		// Human-readable message
		"message": alarm.Message,
		// Core alarm fields
		"id":                    alarm.ID,
		"alarmCode":             alarm.AlarmCode,
		"severity":              alarm.Severity,
		"acknowledged":          alarm.Acknowledged,
		"createdTimestamp":      alarm.CreatedTimestamp,
		"lastModifiedTimestamp": alarm.LastModifiedTimestamp,
		"equipmentId":           alarm.EquipmentID,
		"equipmentName":         alarm.EquipmentName,
		"equipmentType":         alarm.EquipmentType,
		"equipmentIpAddress":    alarm.EquipmentIPAddress,
		"locationName":          alarm.LocationName,
		"generatedBy":           alarm.GeneratedBy,
		"customerId":            alarm.CustomerID,
		"customerName":          alarm.CustomerName,
		"locationId":            alarm.LocationID,
		"originatorType":        alarm.OriginatorType,
		"scopeId":               alarm.ScopeID,
		"scopeType":             alarm.ScopeType,
	}

	return map[string]interface{}{
		"timestamp":     alarm.Timestamp,
		"tag":           CleanDeviceName(alarm.EquipmentName), // Use equipment name as tag
		"componentName": alarm.ComponentName,
		"instanceName":  alarm.InstanceName,
		"data":          data,
		"ipAddress":     alarm.EquipmentIPAddress,
		"zone":          MakeSafeDataKey(alarm.Zone),
	}
}

// BatchEdgeCoreAlarms splits alarms into batches
func BatchEdgeCoreAlarms(alarms []EdgeCoreAlarm, batchSize int) [][]EdgeCoreAlarm {
	var batches [][]EdgeCoreAlarm
	for i := 0; i < len(alarms); i += batchSize {
		end := i + batchSize
		if end > len(alarms) {
			end = len(alarms)
		}
		batches = append(batches, alarms[i:end])
	}
	return batches
}

// ConvertToLogDataArray converts EdgeCore alarms to InsightFinder log format (matching tarana pattern)
func ConvertToLogDataArray(alarms []EdgeCoreAlarm) []map[string]interface{} {
	var result []map[string]interface{}
	for _, alarm := range alarms {
		result = append(result, ConvertAlarmToEdgeCoreLog(alarm))
	}
	return result
}
