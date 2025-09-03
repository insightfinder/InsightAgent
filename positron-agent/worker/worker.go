package worker

import (
	"context"
	"fmt"
	"os"
	"sync"
	"time"

	config "github.com/insightfinder/positron-agent/configs"
	"github.com/insightfinder/positron-agent/insightfinder"
	"github.com/insightfinder/positron-agent/pkg/models"
	"github.com/insightfinder/positron-agent/positron"
	"github.com/sirupsen/logrus"
)

type Worker struct {
	config               *config.Config
	positronService      *positron.Service
	insightFinderService *insightfinder.Service
	testMode             bool
	// Stats tracking
	statsLock    sync.RWMutex
	currentStats *CollectionStats
}

type CollectionStats struct {
	TotalEndpoints     int
	TotalDevices       int
	TotalAlarms        int
	ProcessedEndpoints int
	ProcessedDevices   int
	ProcessedAlarms    int
	ErrorCount         int
	StartTime          time.Time
	LastUpdateTime     time.Time
}

func NewWorker(config *config.Config, positronService *positron.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               config,
		positronService:      positronService,
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

	// // Health check before collection
	// if err := w.positronService.HealthCheck(); err != nil {
	// 	logrus.Errorf("Health check failed: %v", err)
	// 	return
	// }

	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	// Collect metrics data (endpoints and devices)
	w.collectMetrics(ctx)

	// Collect log data (alarms)
	w.collectLogs(ctx)

	duration := time.Since(startTime)
	w.statsLock.RLock()
	finalStats := *w.currentStats
	w.statsLock.RUnlock()

	logrus.Infof("Data collection completed: %d endpoints, %d devices, %d alarms processed in %v",
		finalStats.ProcessedEndpoints, finalStats.ProcessedDevices, finalStats.ProcessedAlarms, duration)
}

func (w *Worker) collectMetrics(ctx context.Context) {
	var metricsBuffer []models.MetricData

	// Collect endpoint metrics
	logrus.Info("Collecting endpoint metrics...")
	endpoints, err := w.positronService.GetEndpoints()
	if err != nil {
		logrus.Errorf("Failed to get endpoints: %v", err)
		w.updateErrorCount()
		return
	}

	w.statsLock.Lock()
	w.currentStats.TotalEndpoints = len(endpoints)
	w.statsLock.Unlock()

	for _, endpoint := range endpoints {
		metric := endpoint.ToMetricData()
		metricsBuffer = append(metricsBuffer, *metric)

		w.statsLock.Lock()
		w.currentStats.ProcessedEndpoints++
		w.statsLock.Unlock()
	}

	// Collect device metrics
	logrus.Info("Collecting device metrics...")
	devices, err := w.positronService.GetDevices()
	if err != nil {
		logrus.Errorf("Failed to get devices: %v", err)
		w.updateErrorCount()
		return
	}

	w.statsLock.Lock()
	w.currentStats.TotalDevices = len(devices)
	w.statsLock.Unlock()

	for _, device := range devices {
		metric := device.ToMetricData()
		metricsBuffer = append(metricsBuffer, *metric)

		w.statsLock.Lock()
		w.currentStats.ProcessedDevices++
		w.statsLock.Unlock()
	}

	// Send metrics data
	if w.testMode {
		w.saveMetricsToFile(metricsBuffer)
	} else {
		if err := w.sendMetrics(metricsBuffer); err != nil {
			logrus.Errorf("Failed to send metrics: %v", err)
			w.updateErrorCount()
		} else {
			logrus.Infof("Successfully sent %d metrics", len(metricsBuffer))
		}
	}
}

func (w *Worker) collectLogs(ctx context.Context) {
	// Collect alarm logs
	logrus.Info("Collecting alarm logs...")
	alarms, err := w.positronService.GetAlarms()
	if err != nil {
		logrus.Errorf("Failed to get alarms: %v", err)
		w.updateErrorCount()
		return
	}

	w.statsLock.Lock()
	w.currentStats.TotalAlarms = len(alarms)
	w.statsLock.Unlock()

	// // Get devices to create a mapping from system name or serial number to IP address
	// devices, err := w.positronService.GetDevices()
	// if err != nil {
	// 	logrus.Warnf("Failed to get devices for IP correlation: %v", err)
	// 	devices = nil
	// }

	// // Create device mapping for IP address correlation
	// deviceIPMap := make(map[string]string)
	// for _, device := range devices {
	// 	// Map by device name and IP if available
	// 	if device.IPAddress != "" {
	// 		deviceIPMap[device.Name] = device.IPAddress
	// 	}
	// }

	var logData []map[string]interface{}
	for _, alarm := range alarms {
		logEntry := alarm.ToLogData()

		// // Try to correlate alarm with device IP address and add it directly to the log entry
		// if ip, exists := deviceIPMap[alarm.SystemName]; exists && ip != "" {
		// 	logEntry["ipAddress"] = ip
		// 	logrus.Debugf("Correlated alarm for system %s with IP %s", alarm.SystemName, ip)
		// }

		logData = append(logData, logEntry)

		w.statsLock.Lock()
		w.currentStats.ProcessedAlarms++
		w.statsLock.Unlock()
	}

	// Send log data
	if w.testMode {
		w.saveLogsToFile(logData)
	} else {
		if err := w.sendLogs(logData); err != nil {
			logrus.Errorf("Failed to send logs: %v", err)
			w.updateErrorCount()
		} else {
			logrus.Infof("Successfully sent %d log entries", len(logData))
		}
	}
}

func (w *Worker) sendMetrics(metrics []models.MetricData) error {
	if len(metrics) == 0 {
		return nil
	}

	return w.insightFinderService.SendMetricDataBatch(metrics)
}

func (w *Worker) sendLogs(logs []map[string]interface{}) error {
	if len(logs) == 0 {
		return nil
	}

	return w.insightFinderService.SendLogDataBatch(logs)
}

func (w *Worker) saveMetricsToFile(metrics []models.MetricData) {
	filename := fmt.Sprintf("positron_metrics_%d.json", time.Now().Unix())
	w.saveDataToFile(filename, metrics)
}

func (w *Worker) saveLogsToFile(logs []map[string]interface{}) {
	filename := fmt.Sprintf("positron_logs_%d.json", time.Now().Unix())
	w.saveDataToFile(filename, logs)
}

func (w *Worker) saveDataToFile(filename string, data interface{}) {
	// Implementation for saving to file in test mode
	logrus.Infof("Test mode: would save data to %s", filename)
	// TODO: Implement actual file saving if needed
}

func (w *Worker) updateErrorCount() {
	w.statsLock.Lock()
	w.currentStats.ErrorCount++
	w.statsLock.Unlock()
}
