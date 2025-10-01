package worker

import (
	"context"
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
		chunkSize:            1000, // Default chunk size for bulk processing
		maxBufferSize:        1000, // Default buffer size for metrics
		currentStats:         &CollectionStats{},
	}
}

// Configure streaming parameters
func (w *Worker) SetStreamingConfig(chunkSize, maxBufferSize int) {
	w.chunkSize = chunkSize
	w.maxBufferSize = maxBufferSize
	logrus.Infof("Streaming configured: chunk size=%d, buffer size=%d", chunkSize, maxBufferSize)
}

func (w *Worker) Start(quit <-chan os.Signal) {
	// Initialize and validate InsightFinder connection
	logrus.Info("Initializing InsightFinder connection...")

	// Create project if it doesn't exist
	if !w.insightFinderService.CreateProjectIfNotExist() {
		logrus.Fatal("Failed to create/verify InsightFinder project")
		return
	}

	logrus.Info("InsightFinder connection established successfully")

	// Use sampling_interval from InsightFinder config instead of collection_interval
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	ticker := time.NewTicker(samplingInterval)
	defer ticker.Stop()

	logrus.Infof("Starting data collection with %d second intervals", w.config.InsightFinder.SamplingInterval)

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

	// First, fetch all client data for RSSI/SNR enrichment
	logrus.Info("Fetching client data for RSSI/SNR enrichment...")
	clientMap, clientErr := w.ruckusService.GetAllClientsWithRSSISNR(ctx)
	if clientErr != nil {
		logrus.Errorf("Failed to fetch client data: %v", clientErr)
		logrus.Info("Continuing without client enrichment data...")
		clientMap = make(map[string][]models.ClientInfo)
	} else {
		logrus.Infof("Successfully fetched client data for %d APs", len(clientMap))
	}

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
		// Enrich AP data with client metrics (RSSI/SNR)
		enrichedChunk := ruckus.EnrichAPDataWithClientMetrics(apChunk, clientMap)

		// Update stats
		w.updateStats(enrichedChunk)

		// Convert to metrics
		var chunkMetrics []models.MetricData
		for _, ap := range enrichedChunk {
			metric := ap.ToMetricData(w.ruckusService.Config.SendComponentNameAsAP)
			chunkMetrics = append(chunkMetrics, *metric)
		}

		// Process zone mappings
		chunkMetrics = models.ProcessZoneMappings(chunkMetrics)

		if w.testMode {
			// Write chunk to test file
			if err := w.writeChunkToTestFile(rawDataFile, enrichedChunk, &firstChunk); err != nil {
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
