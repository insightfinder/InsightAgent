package worker

import (
	"encoding/json"
	"fmt"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// ----------- This file contains the worker methods for collecting and sending data ------------
// It is not being used in the current implementation, but is kept for backward compatibility and future use.

// Legacy method for backward compatibility
func (w *Worker) collectAndSend() {
	w.collectAndSendStreaming()
}

// Get current collection progress (useful for monitoring)
func (w *Worker) GetCollectionProgress() CollectionStats {
	w.statsLock.RLock()
	defer w.statsLock.RUnlock()
	return *w.currentStats
}

// Add method to collect and process all data in non-streaming mode (for testing)
func (w *Worker) collectAllBulk() error {
	logrus.Info("Starting bulk collection of all AP data")

	details, err := w.ruckusService.GetAllAPDetailsBulk()
	if err != nil {
		return fmt.Errorf("failed to get all AP details: %v", err)
	}

	logrus.Infof("Retrieved %d AP details in bulk", len(details))

	// Update stats
	w.updateStats(details)

	// Convert to metrics
	var metrics []models.MetricData
	for _, ap := range details {
		metric := ap.ToMetricData(w.ruckusService.Config.SendComponentNameAsAP, &w.config.MetricFilter)
		metrics = append(metrics, *metric)
	}

	// Process zone mappings
	metrics = models.ProcessZoneMappings(metrics)

	if w.testMode {
		// Save to test file
		testFile, err := w.createTestFile("bulk_all_data")
		if err != nil {
			return fmt.Errorf("failed to create test file: %v", err)
		}
		defer testFile.Close()

		data, err := json.MarshalIndent(details, "", "  ")
		if err != nil {
			return fmt.Errorf("failed to marshal test data: %v", err)
		}

		_, err = testFile.Write(data)
		return err
	} else {
		return w.sendBufferedMetrics(metrics)
	}
}

// Update any other references to use sampling interval
func (w *Worker) logCollectionStats() {
	logrus.Infof("Collection cycle stats:")
	logrus.Infof("  Sampling interval: %d seconds", w.config.InsightFinder.SamplingInterval)
	logrus.Infof("  Test mode: %v", w.testMode)
	logrus.Infof("  Chunk size: %d", w.chunkSize)
}
