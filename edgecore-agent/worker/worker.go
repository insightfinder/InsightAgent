package worker

import (
	"os"
	"sync"
	"time"

	config "github.com/insightfinder/edgecore-agent/configs"
	"github.com/insightfinder/edgecore-agent/edgecore"
	"github.com/insightfinder/edgecore-agent/insightfinder"
	"github.com/insightfinder/edgecore-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

type Worker struct {
	config               *config.Config
	edgecoreService      *edgecore.Service
	insightFinderService *insightfinder.Service
	testMode             bool
	// Stats tracking
	statsLock    sync.RWMutex
	currentStats *CollectionStats
}

type CollectionStats struct {
	TotalDevices     int
	TotalMetrics     int
	TotalAlarms      int
	ProcessedDevices int
	ProcessedMetrics int
	ProcessedAlarms  int
	ErrorCount       int
	StartTime        time.Time
	LastUpdateTime   time.Time
}

func NewWorker(config *config.Config, edgecoreService *edgecore.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               config,
		edgecoreService:      edgecoreService,
		insightFinderService: ifService,
		testMode:             false,
		currentStats:         &CollectionStats{},
	}
}

func (w *Worker) Start(quit <-chan os.Signal) {
	// Initialize and validate InsightFinder connection
	logrus.Info("Initializing InsightFinder connection...")

	// Create metrics project if it doesn't exist
	if !w.insightFinderService.CreateMetricsProjectIfNotExist() {
		logrus.Fatal("Failed to create/verify InsightFinder metrics project")
		return
	}

	// Create logs project if it doesn't exist
	if !w.insightFinderService.CreateLogsProjectIfNotExist() {
		logrus.Fatal("Failed to create/verify InsightFinder logs project")
		return
	}

	logrus.Info("InsightFinder connection established successfully")

	// Use sampling_interval from InsightFinder config
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	ticker := time.NewTicker(samplingInterval)
	defer ticker.Stop()

	logrus.Infof("Starting data collection with %d second intervals", w.config.InsightFinder.SamplingInterval)

	// Run initial collection
	w.collectAndSendData()

	for {
		select {
		case <-ticker.C:
			w.collectAndSendData()
		case <-quit:
			logrus.Info("Worker received shutdown signal")
			return
		}
	}
}

func (w *Worker) collectAndSendData() {
	logrus.Info("Starting data collection cycle")
	startTime := time.Now()

	// Initialize stats
	w.statsLock.Lock()
	w.currentStats = &CollectionStats{
		StartTime:      startTime,
		LastUpdateTime: startTime,
	}
	w.statsLock.Unlock()

	// Step 1: Get zones once for both metrics and alarms
	logrus.Debug("Fetching zones (customers) for service provider - shared for metrics and alarms")
	zones, err := w.edgecoreService.GetCustomersForServiceProvider()
	if err != nil {
		logrus.Errorf("Failed to get zones: %v", err)
		w.incrementErrorCount()
		return
	}

	logrus.Debugf("Found %d zones for concurrent metrics and alarms collection", len(zones))

	// Step 2: Collect metrics and alarms concurrently using the same zones
	var wg sync.WaitGroup
	var allMetrics []edgecore.MetricData
	var allAlarms []edgecore.Alarm
	var metricsErr, alarmsErr error

	// Launch metrics collection in goroutine
	wg.Add(1)
	go func() {
		defer wg.Done()
		logrus.Debug("Starting concurrent EdgeCore metrics collection...")
		allMetrics, metricsErr = w.edgecoreService.GetAllMetrics(zones)
		if metricsErr != nil {
			logrus.Errorf("Failed to get metrics: %v", metricsErr)
			w.incrementErrorCount()
		} else {
			logrus.Infof("Collected %d metric data points", len(allMetrics))
		}
	}()

	// Launch alarms collection in goroutine
	wg.Add(1)
	go func() {
		defer wg.Done()
		logrus.Debug("Starting concurrent EdgeCore alarms collection...")
		allAlarms, alarmsErr = w.edgecoreService.GetAlarms(zones)
		if alarmsErr != nil {
			logrus.Errorf("Failed to get alarms: %v", alarmsErr)
			w.incrementErrorCount()
		} else {
			logrus.Infof("Collected %d alarms", len(allAlarms))
		}
	}()

	// Wait for both collections to complete
	wg.Wait()

	// Update stats
	w.statsLock.Lock()
	w.currentStats.TotalMetrics = len(allMetrics)
	w.currentStats.TotalAlarms = len(allAlarms)
	w.statsLock.Unlock()

	// Step 3: Process and send data concurrently
	var sendWg sync.WaitGroup

	// Send metrics if collection was successful
	if metricsErr == nil && len(allMetrics) > 0 {
		sendWg.Add(1)
		go func() {
			defer sendWg.Done()
			w.processAndSendMetrics(allMetrics)
		}()
	} else if len(allMetrics) == 0 && metricsErr == nil {
		logrus.Warn("No metrics found, skipping metrics processing")
	}

	// Send alarms if collection was successful
	if alarmsErr == nil && len(allAlarms) > 0 {
		sendWg.Add(1)
		go func() {
			defer sendWg.Done()
			w.processAndSendAlarms(allAlarms, zones)
		}()
	} else if len(allAlarms) == 0 && alarmsErr == nil {
		logrus.Debug("No alarms found, skipping alarms processing")
	}

	// Wait for both send operations to complete
	sendWg.Wait()

	// Log completion stats
	duration := time.Since(startTime)
	logrus.Infof("Concurrent data collection cycle completed in %v", duration)
}

func (w *Worker) processAndSendMetrics(metrics []edgecore.MetricData) {
	logrus.Info("Processing and sending metrics to InsightFinder")

	// Convert EdgeCore metrics to InsightFinder format
	ifMetrics := w.convertToIFMetrics(metrics)

	w.statsLock.Lock()
	w.currentStats.ProcessedMetrics = len(ifMetrics)
	w.statsLock.Unlock()

	logrus.Debugf("Converted %d EdgeCore metrics to InsightFinder format", len(ifMetrics))

	if len(ifMetrics) == 0 {
		logrus.Warn("No metrics to send")
		return
	}

	// Send metrics to InsightFinder in batches
	batchSize := 10000 // Adjust based on your needs
	batches := models.BatchEdgeCoreMetrics(ifMetrics, batchSize)

	for i, batch := range batches {
		logrus.Debugf("Sending metrics batch %d/%d (%d metrics)", i+1, len(batches), len(batch))

		ifMetrics := models.ConvertToMetricDataArray(batch)

		err := w.insightFinderService.SendMetrics(ifMetrics)
		if err == nil {
			w.statsLock.Lock()
			w.currentStats.ProcessedMetrics += len(batch)
			w.statsLock.Unlock()
			logrus.Debugf("Successfully sent metrics batch %d", i+1)
		} else {
			logrus.Errorf("Failed to send metrics batch %d", i+1)
			w.incrementErrorCount()
		}
	}

}

// processAndSendAlarms processes and sends alarms to InsightFinder
func (w *Worker) processAndSendAlarms(alarms []edgecore.Alarm, zones []edgecore.Zone) {
	logrus.Debug("Processing alarms for InsightFinder")

	// Create a mapping from customer ID to customer name using zones data
	customerIDToName := make(map[string]string)
	for _, zone := range zones {
		customerIDToName[zone.ID] = zone.Name
	}

	// Convert to flattened EdgeCore alarm format
	var allAlarms []models.EdgeCoreAlarm
	for _, alarm := range alarms {
		// Convert GraphQL alarm structure to flattened EdgeCore alarm model
		edgecoreAlarm := models.EdgeCoreAlarm{
			// Core alarm identification
			ID:           alarm.ID,
			AlarmCode:    alarm.Attributes.AlarmCode,
			Severity:     alarm.Attributes.Severity,
			Acknowledged: alarm.Attributes.Acknowledged,

			// Timestamps
			CreatedTimestamp:      alarm.Attributes.CreatedTimestamp,
			LastModifiedTimestamp: alarm.Attributes.LastModifiedTimestamp,

			// Equipment information (flattened from nested structure)
			EquipmentID:        alarm.Attributes.EquipmentID,
			EquipmentName:      alarm.Attributes.Equipment.Name,
			EquipmentType:      alarm.Attributes.Equipment.EquipmentType,
			EquipmentIPAddress: alarm.Attributes.Equipment.Status.Protocol.Details.ReportedIPV4Addr,
			LocationName:       alarm.Attributes.Equipment.Location.Name,

			// Alarm details (flattened from interface{} JSON)
			Message:     extractStringFromDetails(alarm.Attributes.Details, "message"),
			GeneratedBy: extractStringFromDetails(alarm.Attributes.Details, "generatedBy"),

			// Organizational information
			CustomerID:     alarm.Attributes.CustomerID,
			CustomerName:   customerIDToName[alarm.Attributes.CustomerID], // Get customer name from zones mapping
			LocationID:     alarm.Attributes.LocationID,
			OriginatorType: alarm.Attributes.OriginatorType,
			ScopeID:        alarm.Attributes.ScopeID,
			ScopeType:      alarm.Attributes.ScopeType,

			// InsightFinder specific fields - using equipment info for consistency
			Zone:          customerIDToName[alarm.Attributes.CustomerID], // Use customer name as zone
			ComponentName: alarm.Attributes.Equipment.EquipmentType,
			InstanceName:  alarm.Attributes.Equipment.Name,
		}

		edgecoreAlarm.Timestamp = time.Now().Unix()

		allAlarms = append(allAlarms, edgecoreAlarm)
	}

	w.statsLock.Lock()
	w.currentStats.TotalAlarms = len(allAlarms)
	w.statsLock.Unlock()

	logrus.Debugf("Collected %d alarms", len(allAlarms))

	if len(allAlarms) == 0 {
		logrus.Info("No alarms to send")
		return
	}

	// Send alarms to InsightFinder as logs in batches
	batchSize := 500 // Smaller batch size for logs
	batches := models.BatchEdgeCoreAlarms(allAlarms, batchSize)

	for i, batch := range batches {
		logrus.Debugf("Sending alarms batch %d/%d (%d alarms)", i+1, len(batches), len(batch))

		ifLogs := models.ConvertToLogDataArray(batch)

		// Send logs directly using the map format (matching tarana pattern)
		err := w.insightFinderService.SendLogDataRaw(ifLogs)
		if err == nil {
			w.statsLock.Lock()
			w.currentStats.ProcessedAlarms += len(batch)
			w.statsLock.Unlock()
			logrus.Debugf("Successfully sent alarms batch %d", i+1)
		} else {
			logrus.Errorf("Failed to send alarms batch %d: %v", i+1, err)
			w.incrementErrorCount()
		}
	}

	logrus.Debug("Completed alarms collection and sending")
}

// extractStringFromDetails safely extracts a string value from the details interface{}
func extractStringFromDetails(details interface{}, key string) string {
	if details == nil {
		return ""
	}

	if detailsMap, ok := details.(map[string]interface{}); ok {
		if value, exists := detailsMap[key]; exists {
			if str, ok := value.(string); ok {
				return str
			}
		}
	}

	return ""
}

func (w *Worker) incrementErrorCount() {
	w.statsLock.Lock()
	w.currentStats.ErrorCount++
	w.statsLock.Unlock()
}

func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled")
}

func (w *Worker) GetStats() CollectionStats {
	w.statsLock.RLock()
	defer w.statsLock.RUnlock()
	return *w.currentStats
}

// convertToIFMetrics converts EdgeCore metrics to InsightFinder format
func (w *Worker) convertToIFMetrics(metrics []edgecore.MetricData) []models.EdgeCoreMetric {
	var ifMetrics []models.EdgeCoreMetric
	for _, metric := range metrics {
		ifMetrics = append(ifMetrics, models.EdgeCoreMetric{
			InstanceName:  metric.InstanceName,
			ComponentName: metric.ComponentName,
			MetricName:    metric.MetricName,
			MetricValue:   metric.MetricValue,
			Timestamp:     metric.Timestamp,
			Zone:          metric.Zone,
			IPAddress:     metric.IPAddress,
		})
	}
	return ifMetrics
}
