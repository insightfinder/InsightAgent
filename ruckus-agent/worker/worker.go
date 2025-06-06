package worker

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sync"
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
	testMode             bool
	// Add streaming configuration
	chunkSize     int
	maxBufferSize int
	// Stats tracking
	statsLock    sync.RWMutex
	currentStats *CollectionStats
}

type CollectionStats struct {
	TotalAPs       int
	ProcessedAPs   int
	OnlineAPs      int
	FlaggedAPs     int
	TotalClients   int
	HighAirtime24G int
	HighAirtime5G  int
	ErrorCount     int
	StartTime      time.Time
	LastUpdateTime time.Time
}

func NewWorker(config *config.Config, ruckusService *ruckus.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               config,
		ruckusService:        ruckusService,
		insightFinderService: ifService,
		testMode:             false,
		chunkSize:            100, // Default chunk size for bulk processing
		maxBufferSize:        500, // Default buffer size for metrics
		currentStats:         &CollectionStats{},
	}
}

// Enable test mode for development/testing
func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled - data will be saved to files instead of sent to InsightFinder")
}

// Configure streaming parameters
func (w *Worker) SetStreamingConfig(chunkSize, maxBufferSize int) {
	w.chunkSize = chunkSize
	w.maxBufferSize = maxBufferSize
	logrus.Infof("Streaming configured: chunk size=%d, buffer size=%d", chunkSize, maxBufferSize)
}

func (w *Worker) Start(quit <-chan os.Signal) {
	ticker := time.NewTicker(time.Duration(w.config.Agent.CollectionInterval) * time.Second)
	defer ticker.Stop()

	// Run initial collection
	w.collectAndSendStreaming()

	for {
		select {
		case <-ticker.C:
			w.collectAndSendStreaming()
		case <-quit:
			logrus.Info("Worker received shutdown signal")
			return
		}
	}
}

// New streaming collection method using bulk query
func (w *Worker) collectAndSendStreaming() {
	logrus.Info("Starting streaming data collection cycle with bulk query")
	startTime := time.Now()

	// Initialize stats
	w.statsLock.Lock()
	w.currentStats = &CollectionStats{
		StartTime:      startTime,
		LastUpdateTime: startTime,
	}
	w.statsLock.Unlock()

	// Health check before collection
	if err := w.ruckusService.HealthCheck(); err != nil {
		logrus.Errorf("Health check failed: %v", err)
		return
	}

	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Process metrics buffer
	var metricsBuffer []models.MetricData
	var bufferMutex sync.Mutex

	// Test mode file handles
	var rawDataFile *os.File
	var err error

	if w.testMode {
		rawDataFile, err = w.createTestFile("bulk_ap_data")
		if err != nil {
			logrus.Errorf("Failed to create test file: %v", err)
			return
		}
		defer rawDataFile.Close()

		// Start JSON array
		rawDataFile.WriteString("[\n")
	}

	var firstChunk bool = true
	totalProcessed := 0

	// Processor function for each chunk
	processor := func(apChunk []models.APDetail) error {
		// Update stats
		w.updateStats(apChunk)

		// Convert to metrics
		var chunkMetrics []models.MetricData
		for _, ap := range apChunk {
			metric := ap.ToMetricData()
			chunkMetrics = append(chunkMetrics, *metric)
		}

		if w.testMode {
			// Write chunk to test file
			if err := w.writeChunkToTestFile(rawDataFile, apChunk, &firstChunk); err != nil {
				return fmt.Errorf("failed to write test data: %v", err)
			}
		} else {
			// Add to buffer for production sending
			bufferMutex.Lock()
			metricsBuffer = append(metricsBuffer, chunkMetrics...)

			// Send buffer if it's getting full
			if len(metricsBuffer) >= w.maxBufferSize {
				if err := w.sendBufferedMetrics(metricsBuffer); err != nil {
					logrus.Errorf("Failed to send buffered metrics: %v", err)
					bufferMutex.Unlock()
					return err
				}
				metricsBuffer = metricsBuffer[:0] // Clear buffer
			}
			bufferMutex.Unlock()
		}

		totalProcessed += len(apChunk)
		logrus.Infof("Processed %d APs (total: %d)", len(apChunk), totalProcessed)

		return nil
	}

	// Use the new bulk streaming method instead of individual AP queries
	err = w.ruckusService.GetAllAPDetailsStreamingBulk(ctx, processor, w.chunkSize)
	if err != nil {
		logrus.Errorf("Bulk streaming collection failed: %v", err)
		return
	}

	// Send remaining buffered metrics in production mode
	if !w.testMode {
		bufferMutex.Lock()
		if len(metricsBuffer) > 0 {
			if err := w.sendBufferedMetrics(metricsBuffer); err != nil {
				logrus.Errorf("Failed to send final buffered metrics: %v", err)
			}
		}
		bufferMutex.Unlock()
	}

	// Finalize test mode files
	if w.testMode {
		rawDataFile.WriteString("\n]")
		if err := w.saveStreamingStats(); err != nil {
			logrus.Errorf("Failed to save streaming stats: %v", err)
		}
	}

	duration := time.Since(startTime)
	w.statsLock.RLock()
	finalStats := *w.currentStats
	w.statsLock.RUnlock()

	logrus.Infof("Bulk streaming collection completed: %d APs processed in %v (%.2f APs/sec)",
		finalStats.ProcessedAPs, duration, float64(finalStats.ProcessedAPs)/duration.Seconds())
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
		metric := ap.ToMetricData()
		metrics = append(metrics, *metric)
	}

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
		if ap.ConnectionStatus == "Connect" {
			w.currentStats.OnlineAPs++
		}
		if ap.Status == "Flagged" {
			w.currentStats.FlaggedAPs++
		}
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
		metric := ap.ToMetricData()
		metrics = append(metrics, *metric)
	}

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
