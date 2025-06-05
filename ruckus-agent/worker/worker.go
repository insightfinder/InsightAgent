package worker

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	config "github.com/insightfinder/ruckus-agent/configs"
	"github.com/insightfinder/ruckus-agent/insightfinder"
	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/insightfinder/ruckus-agent/ruckus"
	"github.com/sirupsen/logrus"
)

type Worker struct {
	config               *config.Config
	ruckusService        *ruckus.Service
	insightFinderService *insightfinder.Service
	testMode             bool // Add test mode flag
}

func NewWorker(config *config.Config, ruckusService *ruckus.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               config,
		ruckusService:        ruckusService,
		insightFinderService: ifService,
		testMode:             false, // Default to false
	}
}

// Enable test mode for development/testing
func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled - data will be saved to files instead of sent to InsightFinder")
}

func (w *Worker) Start(quit <-chan os.Signal) {
	ticker := time.NewTicker(time.Duration(w.config.Agent.CollectionInterval) * time.Second)
	defer ticker.Stop()

	// Run initial collection
	w.collectAndSend()

	for {
		select {
		case <-ticker.C:
			w.collectAndSend()
		case <-quit:
			logrus.Info("Worker received shutdown signal")
			return
		}
	}
}

func (w *Worker) collectAndSend() {
	logrus.Info("Starting data collection cycle")
	startTime := time.Now()

	// Health check before collection
	if err := w.ruckusService.HealthCheck(); err != nil {
		logrus.Errorf("Health check failed: %v", err)
		return
	}

	// Collect AP details
	apDetails, err := w.ruckusService.GetAllAPDetails()
	if err != nil {
		logrus.Errorf("Failed to collect AP details: %v", err)
		return
	}

	if len(apDetails) == 0 {
		logrus.Warn("No AP details collected")
		return
	}

	// Convert to metric data
	var metrics []models.MetricData
	for _, ap := range apDetails {
		metric := ap.ToMetricData()
		metrics = append(metrics, *metric)
	}

	// === TEST MODE: Save to files instead of sending to InsightFinder ===
	if w.testMode {
		if err := w.saveTestData(apDetails, metrics); err != nil {
			logrus.Errorf("Failed to save test data: %v", err)
			return
		}
	} else {
		// === PRODUCTION MODE: Send to InsightFinder ===
		// Send to InsightFinder
		if err := w.insightFinderService.SendMetrics(metrics); err != nil {
			logrus.Errorf("Failed to send metrics to InsightFinder: %v", err)
			return
		}
	}

	duration := time.Since(startTime)
	logrus.Infof("Successfully collected and processed %d AP metrics in %v", len(metrics), duration)
}

// === TEST MODE FUNCTIONS - Remove these when testing is complete ===

func (w *Worker) saveTestData(apDetails []models.APDetail, metrics []models.MetricData) error {
	timestamp := time.Now().Format("20060102_150405")

	// Create test_data directory if it doesn't exist
	if err := os.MkdirAll("test_data", 0755); err != nil {
		return fmt.Errorf("failed to create test_data directory: %v", err)
	}

	// Save raw AP details
	rawFilename := fmt.Sprintf("test_data/raw_ap_data_%s.json", timestamp)
	rawData, err := json.MarshalIndent(apDetails, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal AP details: %v", err)
	}
	if err := os.WriteFile(rawFilename, rawData, 0644); err != nil {
		return fmt.Errorf("failed to write raw data file: %v", err)
	}

	// Save basic statistics
	statsFilename := fmt.Sprintf("test_data/stats_%s.txt", timestamp)
	stats := w.generateBasicStats(apDetails)
	if err := os.WriteFile(statsFilename, []byte(stats), 0644); err != nil {
		return fmt.Errorf("failed to write stats file: %v", err)
	}

	logrus.Infof("Test data saved:")
	logrus.Infof("  Raw data: %s (%d APs)", rawFilename, len(apDetails))
	logrus.Infof("  Statistics: %s", statsFilename)

	return nil
}

func (w *Worker) generateBasicStats(apDetails []models.APDetail) string {
	totalAPs := len(apDetails)
	onlineAPs := 0
	flaggedAPs := 0
	totalClients := 0
	highAirtime24G := 0
	highAirtime5G := 0

	for _, ap := range apDetails {
		if ap.ConnectionStatus == "Connect" {
			onlineAPs++
		}
		if ap.Status == "Flagged" || ap.IsOverallHealthFlagged {
			flaggedAPs++
		}
		totalClients += ap.NumClients
		if ap.Airtime24G > 80 {
			highAirtime24G++
		}
		if ap.Airtime5G > 80 {
			highAirtime5G++
		}
	}

	stats := fmt.Sprintf(`Ruckus AP Collection Statistics - %s
========================================

Total APs: %d
Online APs: %d (%.1f%%)
Flagged APs: %d (%.1f%%)
Total Clients: %d
Average Clients per AP: %.1f

High Airtime (>80%%):
  2.4GHz Band: %d APs
  5GHz Band: %d APs

Collection completed at: %s
`,
		time.Now().Format("2006-01-02 15:04:05"),
		totalAPs,
		onlineAPs, float64(onlineAPs)/float64(totalAPs)*100,
		flaggedAPs, float64(flaggedAPs)/float64(totalAPs)*100,
		totalClients,
		float64(totalClients)/float64(totalAPs),
		highAirtime24G,
		highAirtime5G,
		time.Now().Format("2006-01-02 15:04:05"))

	return stats
}

// === END TEST MODE FUNCTIONS ===
