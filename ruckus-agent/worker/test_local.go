package worker

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// ------- Worker methods for testing and bulk query functionality -------

// Enable test mode for development/testing
func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled - data will be saved to files instead of sent to InsightFinder")
}

// Add method for testing bulk query functionality
func (w *Worker) TestBulkQuery() error {
	logrus.Info("Testing bulk query functionality")
	return w.ruckusService.TestBulkQuery()
}

// Add method for getting specific MAC addresses if needed
func (w *Worker) collectSpecificMACs(macAddresses []string) error {
	logrus.Infof("Collecting data for %d specific MAC addresses", len(macAddresses))

	batchSize := 10 // Process MACs in batches of 10
	details, err := w.ruckusService.GetAPDetailsByMACs(macAddresses, batchSize)
	if err != nil {
		return fmt.Errorf("failed to get AP details for specific MACs: %v", err)
	}

	logrus.Infof("Retrieved %d AP details for %d requested MACs", len(details), len(macAddresses))

	// Convert to metrics and send
	var metrics []models.MetricData
	for _, ap := range details {
		metric := ap.ToMetricData(w.ruckusService.Config.SendComponentNameAsAP)
		metrics = append(metrics, *metric)
	}

	// zone mapping
	metrics = models.ProcessZoneMappings(metrics)

	if w.testMode {
		// Save to test file
		testFile, err := w.createTestFile("specific_macs_data")
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

// Update statistics with new chunk
func (w *Worker) updateStats(apChunk []models.APDetail) {
	w.statsLock.Lock()
	defer w.statsLock.Unlock()

	w.currentStats.ProcessedAPs += len(apChunk)
	w.currentStats.LastUpdateTime = time.Now()

	for _, ap := range apChunk {
		w.currentStats.TotalClients += ap.NumClients
		if ap.Airtime24G > 80 {
			w.currentStats.HighAirtime24G++
		}
		if ap.Airtime5G > 80 {
			w.currentStats.HighAirtime5G++
		}
	}
}

// Send buffered metrics to InsightFinder
func (w *Worker) sendBufferedMetrics(metrics []models.MetricData) error {
	if len(metrics) == 0 {
		return nil
	}

	logrus.Infof("Sending batch of %d metrics to InsightFinder", len(metrics))
	return w.insightFinderService.SendMetrics(metrics)
}

// Create test file with timestamp
func (w *Worker) createTestFile(prefix string) (*os.File, error) {
	timestamp := time.Now().Format("20060102_150405")

	// Create test_data directory if it doesn't exist
	if err := os.MkdirAll("test_data", 0755); err != nil {
		return nil, fmt.Errorf("failed to create test_data directory: %v", err)
	}

	filename := fmt.Sprintf("test_data/%s_%s.json", prefix, timestamp)
	return os.Create(filename)
}

// Write chunk to test file
func (w *Worker) writeChunkToTestFile(file *os.File, chunk []models.APDetail, firstChunk *bool) error {
	for i, ap := range chunk {
		if !*firstChunk || i > 0 {
			file.WriteString(",\n")
		}

		data, err := json.MarshalIndent(ap, "  ", "  ")
		if err != nil {
			return err
		}

		file.WriteString("  ")
		file.Write(data)
	}

	*firstChunk = false
	return nil
}

// Save streaming statistics
func (w *Worker) saveStreamingStats() error {
	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("test_data/bulk_streaming_stats_%s.txt", timestamp)

	w.statsLock.RLock()
	stats := *w.currentStats
	w.statsLock.RUnlock()

	duration := stats.LastUpdateTime.Sub(stats.StartTime)

	content := fmt.Sprintf(`Ruckus AP Bulk Streaming Collection Statistics - %s
========================================================

Collection Performance:
  Total APs Processed: %d
  Processing Duration: %v
  Average Speed: %.2f APs/second
  Chunk Size: %d
  Buffer Size: %d
  Collection Method: Bulk Query API

AP Health Summary:
  Online APs: %d (%.1f%%)
  Flagged APs: %d (%.1f%%)
  Total Clients: %d
  Average Clients per AP: %.1f

Performance Issues:
  High 2.4GHz Airtime (>80%%): %d APs
  High 5GHz Airtime (>80%%): %d APs
  Collection Errors: %d

Optimization Benefits:
  API Calls Saved: ~%d individual calls avoided
  Estimated Time Saved: ~%.1f minutes
  Memory Efficiency: Streaming enabled
  Network Efficiency: Bulk data transfer

Started: %s
Completed: %s
`,
		time.Now().Format("2006-01-02 15:04:05"),
		stats.ProcessedAPs,
		duration,
		float64(stats.ProcessedAPs)/duration.Seconds(),
		w.chunkSize,
		w.maxBufferSize,
		stats.OnlineAPs,
		float64(stats.OnlineAPs)/float64(stats.ProcessedAPs)*100,
		stats.FlaggedAPs,
		float64(stats.FlaggedAPs)/float64(stats.ProcessedAPs)*100,
		stats.TotalClients,
		float64(stats.TotalClients)/float64(stats.ProcessedAPs),
		stats.HighAirtime24G,
		stats.HighAirtime5G,
		stats.ErrorCount,
		stats.ProcessedAPs,                 // Approximate API calls saved
		float64(stats.ProcessedAPs)*0.5/60, // Estimated time saved in minutes
		stats.StartTime.Format("2006-01-02 15:04:05"),
		stats.LastUpdateTime.Format("2006-01-02 15:04:05"))

	return os.WriteFile(filename, []byte(content), 0644)
}
