package worker

import (
	"os"
	"sync"
	"time"

	config "github.com/insightfinder/tarana-agent/configs"
	"github.com/insightfinder/tarana-agent/insightfinder"
	"github.com/insightfinder/tarana-agent/pkg/models"
	"github.com/insightfinder/tarana-agent/tarana"
	"github.com/sirupsen/logrus"
)

type Worker struct {
	config               *config.Config
	taranaService        *tarana.Service
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

func NewWorker(config *config.Config, taranaService *tarana.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               config,
		taranaService:        taranaService,
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

	// Health check before collection
	// if err := w.taranaService.HealthCheck(); err != nil {
	// 	logrus.Errorf("Tarana health check failed: %v", err)
	// 	w.incrementErrorCount()
	// 	return
	// }
	// logrus.Debug("Tarana health check passed")

	// Step 1: Get all devices
	devices, err := w.taranaService.GetDevices()
	if err != nil {
		logrus.Errorf("Failed to get devices: %v", err)
		w.incrementErrorCount()
		return
	}

	w.statsLock.Lock()
	w.currentStats.TotalDevices = len(devices)
	w.statsLock.Unlock()

	logrus.Infof("Found %d devices", len(devices))

	if len(devices) == 0 {
		logrus.Warn("No devices found, skipping metric collection")
		return
	}

	// Create device mapping for quick lookup
	deviceMap := models.CreateDeviceMapping(convertToModelDevices(devices))

	// Step 2: Collect metrics
	go w.collectAndSendMetrics(devices, deviceMap)

	// Step 3: Collect logs/alarms
	go w.collectAndSendLogs()

	// Log completion stats
	duration := time.Since(startTime)
	logrus.Infof("Data collection cycle completed in %v", duration)
}

func (w *Worker) collectAndSendMetrics(devices []tarana.Device, deviceMap map[string]models.DeviceInfo) {
	logrus.Info("Starting metrics collection")

	// Extract serial numbers for metrics API
	var serialNumbers []string
	for _, device := range devices {
		serialNumbers = append(serialNumbers, device.SerialNumber)
	}

	// Get metrics from Tarana API
	metricsResp, err := w.taranaService.GetMetrics(serialNumbers)
	if err != nil {
		logrus.Errorf("Failed to get metrics: %v", err)
		w.incrementErrorCount()
		return
	}

	// Convert to internal format
	var allMetrics []models.TaranaMetric
	for _, deviceMetrics := range metricsResp.Data.Items {
		// Find corresponding device info
		deviceInfo, exists := deviceMap[deviceMetrics.DeviceID]
		if !exists {
			logrus.Warnf("Device info not found for device ID: %s", deviceMetrics.DeviceID)
			continue
		}

		// Convert API structures to model structures
		modelDeviceMetrics := models.TaranaDeviceMetrics{
			DeviceID: deviceMetrics.DeviceID,
			KPIs:     convertToModelKPIs(deviceMetrics.KPIs),
		}

		modelDevice := models.TaranaDevice{
			SerialNumber: deviceInfo.SerialNumber,
			Type:         deviceInfo.Type,
			IP:           deviceInfo.IP,
			HostName:     deviceInfo.HostName,
		}

		metrics := models.ConvertDeviceMetricsToIFMetrics(modelDeviceMetrics, modelDevice, w.config.Tarana.KPIs)

		// Log KPI availability for debugging
		if len(deviceMetrics.KPIs) == 0 {
			logrus.Debugf("No KPIs available for device %s", deviceMetrics.DeviceID)
		} else {
			logrus.Debugf("Device %s: %d KPIs available, %d metrics generated",
				deviceMetrics.DeviceID, len(deviceMetrics.KPIs), len(metrics))
		}

		allMetrics = append(allMetrics, metrics...)
	}

	w.statsLock.Lock()
	w.currentStats.TotalMetrics = len(allMetrics)
	w.statsLock.Unlock()

	// Log information about unavailable KPIs if any
	if len(metricsResp.Data.UnavailableKPIs) > 0 {
		logrus.Warnf("Some KPIs were unavailable in this collection cycle:")
		for _, unavailableKPI := range metricsResp.Data.UnavailableKPIs {
			logrus.Warnf("  KPI: %s - Reason: %s", unavailableKPI.KPI, unavailableKPI.Message)
		}
	}

	logrus.Infof("Collected %d metrics from %d devices (unavailable KPIs: %d)",
		len(allMetrics), len(metricsResp.Data.Items), len(metricsResp.Data.UnavailableKPIs))

	if len(allMetrics) == 0 {
		logrus.Warn("No metrics to send")
		return
	}

	// Send metrics to InsightFinder in batches
	batchSize := 1000 // Adjust based on your needs
	batches := models.BatchTaranaMetrics(allMetrics, batchSize)

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

	logrus.Infof("Completed metrics collection and sending")
}

func (w *Worker) collectAndSendLogs() {
	logrus.Info("Starting logs/alarms collection")

	// Get alarms from Tarana API
	alarmsResp, err := w.taranaService.GetAlarms()
	if err != nil {
		logrus.Errorf("Failed to get alarms: %v", err)
		w.incrementErrorCount()
		return
	}

	// Convert to internal format
	var allLogs []models.TaranaLog
	for _, alarm := range alarmsResp.Data.Details {
		// Convert API structure to model structure - only using essential fields
		modelAlarm := models.TaranaAlarmDetail{
			// Essential device identification fields
			DeviceIP:           alarm.DeviceIP,
			DeviceHostName:     alarm.DeviceHostName,
			DeviceSerialNumber: alarm.DeviceSerialNumber,
			RadioType:          alarm.RadioType,

			// Core alarm fields
			ID:          alarm.ID,
			Text:        alarm.Text,
			Status:      alarm.Status,
			Severity:    alarm.Severity,
			Category:    alarm.Category,
			TimeCleared: alarm.TimeCleared,
			TimeCreated: alarm.TimeCreated,
			DisplayID:   alarm.DisplayID,
		}

		log := models.ConvertAlarmToIFLog(modelAlarm)
		allLogs = append(allLogs, log)
	}

	w.statsLock.Lock()
	w.currentStats.TotalAlarms = len(allLogs)
	w.statsLock.Unlock()

	logrus.Infof("Collected %d alarms", len(allLogs))

	if len(allLogs) == 0 {
		logrus.Info("No alarms to send")
		return
	}

	// Send logs to InsightFinder in batches
	batchSize := 500 // Smaller batch size for logs
	batches := models.BatchTaranaLogs(allLogs, batchSize)

	for i, batch := range batches {
		logrus.Debugf("Sending logs batch %d/%d (%d logs)", i+1, len(batches), len(batch))

		ifLogs := models.ConvertToLogDataArray(batch)

		err := w.insightFinderService.SendLogDataBatch(ifLogs)
		if err == nil {
			w.statsLock.Lock()
			w.currentStats.ProcessedAlarms += len(batch)
			w.statsLock.Unlock()
			logrus.Debugf("Successfully sent logs batch %d", i+1)
		} else {
			logrus.Errorf("Failed to send logs batch %d", i+1)
			w.incrementErrorCount()
		}
	}

	logrus.Infof("Completed logs collection and sending")
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

// Helper functions to convert API types to model types
func convertToModelDevices(apiDevices []tarana.Device) []models.TaranaDevice {
	var devices []models.TaranaDevice
	for _, apiDevice := range apiDevices {
		devices = append(devices, models.TaranaDevice{
			SerialNumber: apiDevice.SerialNumber,
			Type:         apiDevice.Type,
			IP:           apiDevice.IP,
			HostName:     apiDevice.HostName,
		})
	}
	return devices
}

func convertToModelKPIs(apiKPIs []tarana.KPI) []models.TaranaKPI {
	var kpis []models.TaranaKPI
	for _, apiKPI := range apiKPIs {
		// Convert negative values to positive since InsightFinder only supports positive metrics
		value := apiKPI.Value
		if value < 0 {
			value = -value // Use negation instead of math.Abs to avoid import
		}

		kpis = append(kpis, models.TaranaKPI{
			KPI:               apiKPI.KPI,
			Value:             value,
			Time:              apiKPI.Time,
			SampleAggregation: apiKPI.SampleAggregation,
		})
	}
	return kpis
}
