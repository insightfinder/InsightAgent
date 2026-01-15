package worker

import (
	"fmt"
	"time"

	"github.com/insightfinder/netexperience-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// processCustomer processes metrics for a single customer
func (w *Worker) processCustomer(customer *models.Customer, fromTime, toTime int64) []*models.EquipmentMetrics {
	equipment := w.netexpService.GetCachedEquipmentForCustomer(customer.ID)
	if len(equipment) == 0 {
		logrus.Debugf("No equipment found for customer %s (ID: %d)", customer.Name, customer.ID)
		return nil
	}

	logrus.Debugf("Processing %d equipment items for customer %s", len(equipment), customer.Name)

	// Process equipment in batches
	batchSize := w.config.NetExperience.EquipmentBatchSize
	allMetrics := make([]*models.EquipmentMetrics, 0)

	for i := 0; i < len(equipment); i += batchSize {
		end := i + batchSize
		if end > len(equipment) {
			end = len(equipment)
		}

		batch := equipment[i:end]
		batchIDs := make([]int, len(batch))
		for j, eq := range batch {
			batchIDs[j] = eq.ID
		}

		// Fetch service metrics for this batch
		serviceMetrics, err := w.netexpService.GetServiceMetrics(customer.ID, batchIDs, fromTime, toTime)
		if err != nil {
			logrus.Errorf("Failed to get service metrics for customer %d, batch %d: %v", customer.ID, i/batchSize, err)
			continue
		}

		// Process metrics for each equipment in the batch
		for _, eq := range batch {
			equipmentMetrics := w.processEquipmentMetrics(eq, customer, serviceMetrics)
			if equipmentMetrics != nil {
				allMetrics = append(allMetrics, equipmentMetrics)
			}
		}
	}

	return allMetrics
}

// processEquipmentMetrics processes metrics for a single equipment
func (w *Worker) processEquipmentMetrics(equipment *models.Equipment, customer *models.Customer, serviceMetrics []*models.ServiceMetric) *models.EquipmentMetrics {
	// Filter metrics for this equipment
	var apNodeMetrics *models.ApNodeMetrics
	clientMetrics := make([]*models.ClientMetrics, 0)
	latestTimestamp := int64(0)

	for _, metric := range serviceMetrics {
		if metric.EquipmentID != equipment.ID {
			continue
		}

		if metric.CreatedTimestamp > latestTimestamp {
			latestTimestamp = metric.CreatedTimestamp
		}

		switch metric.DataType {
		case "ApNode":
			if details, ok := metric.Details.(models.ApNodeMetrics); ok {
				// Keep only the most recent ApNode metrics
				if apNodeMetrics == nil || details.SourceTimestampMs > apNodeMetrics.SourceTimestampMs {
					apNodeMetrics = &details
				}
			}
		case "Client":
			if details, ok := metric.Details.(models.ClientMetrics); ok {
				clientMetrics = append(clientMetrics, &details)
			}
		default:
			// Unknown/unsupported types (e.g., SwitchNode) are ignored for now per plan
			logrus.Debugf("Unhandled ServiceMetric dataType: %s", metric.DataType)
		}
	}

	// If no ApNode metrics found, skip this equipment
	if apNodeMetrics == nil {
		logrus.Debugf("No ApNode metrics found for equipment %s (ID: %d)", equipment.Name, equipment.ID)
		return nil
	}

	// Calculate equipment metrics
	result := &models.EquipmentMetrics{
		EquipmentID:   equipment.ID,
		EquipmentName: equipment.Name,
		CustomerID:    customer.ID,
		CustomerName:  customer.Name,
		IPAddress:     equipment.IPAddress,
		Timestamp:     time.UnixMilli(latestTimestamp),
	}

	// Client counts from ApNode metrics
	if apNodeMetrics.ClientMacAddressesPerRadio != nil {
		if clients5G, ok := apNodeMetrics.ClientMacAddressesPerRadio["is5GHz"]; ok {
			result.Clients5GHz = len(clients5G)
		}
		if clients24G, ok := apNodeMetrics.ClientMacAddressesPerRadio["is2dot4GHz"]; ok {
			result.Clients24GHz = len(clients24G)
		}
		result.TotalClients = result.Clients5GHz + result.Clients24GHz
	}

	// Use clientCount from ApNodeMetrics if available
	if apNodeMetrics.ClientCount > 0 {
		result.TotalClients = apNodeMetrics.ClientCount
	}

	// Channel utilization
	if apNodeMetrics.ChannelUtilizationPerRadio != nil {
		if util5G, ok := apNodeMetrics.ChannelUtilizationPerRadio["is5GHz"]; ok {
			result.ChannelUtilization5GHz = util5G
		}
		if util24G, ok := apNodeMetrics.ChannelUtilizationPerRadio["is2dot4GHz"]; ok {
			result.ChannelUtilization24GHz = util24G
		}
	}

	// RSSI metrics from client data
	if len(clientMetrics) > 0 {
		rssiValues := make([]int, 0, len(clientMetrics))
		for _, client := range clientMetrics {
			if client.RSSI != 0 {
				rssiValues = append(rssiValues, client.RSSI)
			}
		}

		if len(rssiValues) > 0 {
			threshold := w.config.NetExperience.MinClientsRSSIThreshold
			result.AverageRSSI, result.ClientsRSSIBelow74, result.ClientsRSSIBelow78, result.ClientsRSSIBelow80,
				result.PercentRSSIBelow74, result.PercentRSSIBelow78, result.PercentRSSIBelow80 =
				models.CalculateRSSIMetrics(rssiValues, threshold)
		}
	}

	return result
}

// sendMetricsToIF sends metrics to InsightFinder
func (w *Worker) sendMetricsToIF(equipmentMetrics []*models.EquipmentMetrics) error {
	if len(equipmentMetrics) == 0 {
		return nil
	}

	// Group metrics by timestamp
	metricsByTimestamp := make(map[int64][]*models.EquipmentMetrics)
	for _, em := range equipmentMetrics {
		ts := em.Timestamp.Unix()
		metricsByTimestamp[ts] = append(metricsByTimestamp[ts], em)
	}

	// Send metrics for each timestamp
	var errors []error
	for timestamp, metrics := range metricsByTimestamp {
		if err := w.sendMetricBatch(timestamp, metrics); err != nil {
			errors = append(errors, err)
		}
	}

	if len(errors) > 0 {
		return fmt.Errorf("failed to send some metric batches: %v", errors)
	}

	return nil
}

// sendMetricBatch sends a batch of metrics for a specific timestamp
func (w *Worker) sendMetricBatch(timestamp int64, metrics []*models.EquipmentMetrics) error {
	// Build metric data for each equipment
	metricDataList := make([]models.MetricData, 0, len(metrics))

	for _, em := range metrics {
		instanceName := models.CleanDeviceName(em.EquipmentName)

		data := map[string]interface{}{
			"Total Clients":              float64(em.TotalClients),
			"Clients 5GHz":               float64(em.Clients5GHz),
			"Clients 2.4GHz":             float64(em.Clients24GHz),
			"Channel Utilization 5GHz":   em.ChannelUtilization5GHz,
			"Channel Utilization 2.4GHz": em.ChannelUtilization24GHz,
			"Average RSSI":               em.AverageRSSI,
			"% Clients RSSI < -74 dBm":   em.PercentRSSIBelow74,
			"% Clients RSSI < -78 dBm":   em.PercentRSSIBelow78,
			"% Clients RSSI < -80 dBm":   em.PercentRSSIBelow80,
		}

		metricData := models.MetricData{
			Timestamp:     timestamp * 1000, // Convert to milliseconds
			InstanceName:  instanceName,
			Data:          data,
			Zone:          em.CustomerName,
			ComponentName: "AP",
			IP:            em.IPAddress,
		}

		metricDataList = append(metricDataList, metricData)
	}

	// Send metrics to InsightFinder
	if err := w.ifService.SendMetrics(metricDataList); err != nil {
		return fmt.Errorf("failed to send metrics to InsightFinder: %w", err)
	}

	return nil
}
