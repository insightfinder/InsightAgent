package worker

import (
	"fmt"
	"os"
	"sync"
	"time"

	config "github.com/insightfinder/loki-agent/configs"
	"github.com/insightfinder/loki-agent/insightfinder"
	"github.com/insightfinder/loki-agent/loki"
	"github.com/insightfinder/loki-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

type Worker struct {
	config               *config.Config
	lokiService          *loki.Service
	insightFinderService *insightfinder.Service
	testMode             bool

	// Stats tracking
	statsLock    sync.RWMutex
	currentStats *models.CollectionStats

	// Simple query tracking without persistence
	lastQueryTimes map[string]time.Time
	queryMutex     sync.RWMutex
}

// NewWorker creates a new worker instance
func NewWorker(cfg *config.Config, lokiService *loki.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               cfg,
		lokiService:          lokiService,
		insightFinderService: ifService,
		testMode:             false,
		currentStats: &models.CollectionStats{
			StartTime: time.Now(),
		},
		lastQueryTimes: make(map[string]time.Time),
	}
}

// Start begins the worker's main processing loop
func (w *Worker) Start(quit <-chan os.Signal) {
	// Initialize InsightFinder connection
	if err := w.insightFinderService.Initialize(); err != nil {
		logrus.Errorf("Failed to initialize InsightFinder service: %v", err)
		return
	}
	logrus.Info("InsightFinder service initialized successfully")

	// Start the main processing ticker using sampling_interval from InsightFinder config
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	ticker := time.NewTicker(samplingInterval)
	defer ticker.Stop()

	logrus.Infof("Worker started. Collection interval: %d seconds", w.config.InsightFinder.SamplingInterval)

	// Process immediately on start
	w.processAllQueries()

	for {
		select {
		case <-quit:
			logrus.Info("Worker received shutdown signal")
			return

		case <-ticker.C:
			w.processAllQueries()
		}
	}
}

// processAllQueries processes all configured queries
func (w *Worker) processAllQueries() {
	w.updateStats(func(stats *models.CollectionStats) {
		stats.LastUpdateTime = time.Now()
	})

	for _, queryConfig := range w.config.Loki.Queries {
		if !queryConfig.Enabled {
			continue
		}

		if err := w.processQuery(queryConfig); err != nil {
			logrus.Errorf("Error processing query '%s': %v", queryConfig.Name, err)
			w.incrementErrorCount(queryConfig.Name)
		}
	}
}

// processQuery processes a single query configuration
func (w *Worker) processQuery(queryConfig config.QueryConfig) error {
	queryStartTime := time.Now()

	// Use sampling interval to determine the time window (like edgecore-agent)
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	end := time.Now()
	start := end.Add(-samplingInterval)

	// Get the last query timestamp for this query
	lastQueryTime := w.getLastQueryTime(queryConfig.Name)

	// If we have a last query time, use it as start to avoid duplicates
	if lastQueryTime != nil && !lastQueryTime.IsZero() {
		if lastQueryTime.After(start) {
			start = *lastQueryTime
		}
	}

	// Skip if start time is after end time (no new data)
	if start.After(end) || start.Equal(end) {
		return nil
	}

	logrus.Infof("Querying '%s' from %s to %s (sampling interval: %ds)",
		queryConfig.Name, start.Format(time.RFC3339), end.Format(time.RFC3339),
		w.config.InsightFinder.SamplingInterval) // Execute Loki query
	queryRequest := loki.QueryRequest{
		Query:     queryConfig.Query,
		Start:     start,
		End:       end,
		Limit:     queryConfig.MaxEntries,
		Direction: "forward",
		Labels:    queryConfig.Labels,
	}

	response, err := w.lokiService.QueryRange(queryRequest)
	if err != nil {
		return fmt.Errorf("Loki query failed: %v", err)
	}

	// Convert response to log entries
	entries, err := w.lokiService.ConvertResponseToLogEntries(response, queryConfig.Labels)
	if err != nil {
		return fmt.Errorf("failed to convert response: %v", err)
	}

	if len(entries) == 0 {
		logrus.Infof("No new log entries found for query '%s'", queryConfig.Name)
		w.updateLastQueryTime(queryConfig.Name, end)
		return nil
	}

	logrus.Infof("Found %d log entries for query '%s'", len(entries), queryConfig.Name)

	// Send to InsightFinder if not in test mode
	if !w.testMode {
		result, err := w.insightFinderService.SendLogData(entries, queryConfig.Labels)
		if err != nil {
			return fmt.Errorf("failed to send data to InsightFinder: %v", err)
		}

		logrus.Infof("Successfully sent %d entries (%d bytes) to InsightFinder in %v",
			result.EntriesSent, result.BytesSent, result.TimeTaken)
	} else {
		logrus.Infof("TEST MODE: Would send %d entries to InsightFinder", len(entries))
	}

	// Update query time tracking
	w.updateLastQueryTime(queryConfig.Name, end)

	// Update stats
	queryDuration := time.Since(queryStartTime)
	w.updateStats(func(stats *models.CollectionStats) {
		stats.TotalQueries++
		stats.TotalLogEntries += len(entries)
		stats.ProcessedEntries += len(entries)
		stats.LastSuccessfulQuery = time.Now()

		// Calculate average query time
		if stats.TotalQueries == 1 {
			stats.AverageQueryTime = queryDuration
		} else {
			stats.AverageQueryTime = (stats.AverageQueryTime + queryDuration) / 2
		}

		// Calculate queries per minute
		elapsed := time.Since(stats.StartTime).Minutes()
		if elapsed > 0 {
			stats.QueriesPerMinute = float64(stats.TotalQueries) / elapsed
		}
	})

	return nil
}

// EnableTestMode enables test mode (doesn't send data to InsightFinder)
func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled - data will not be sent to InsightFinder")
}

// GetStats returns the current collection statistics
func (w *Worker) GetStats() models.CollectionStats {
	w.statsLock.RLock()
	defer w.statsLock.RUnlock()
	return *w.currentStats
}

// Helper methods for query time tracking
func (w *Worker) getLastQueryTime(queryName string) *time.Time {
	w.queryMutex.RLock()
	defer w.queryMutex.RUnlock()

	if t, exists := w.lastQueryTimes[queryName]; exists {
		return &t
	}
	return nil
}

func (w *Worker) updateLastQueryTime(queryName string, timestamp time.Time) {
	w.queryMutex.Lock()
	defer w.queryMutex.Unlock()

	w.lastQueryTimes[queryName] = timestamp
}

func (w *Worker) incrementErrorCount(queryName string) {
	w.updateStats(func(stats *models.CollectionStats) {
		stats.ErrorCount++
	})
}

func (w *Worker) updateStats(updateFunc func(*models.CollectionStats)) {
	w.statsLock.Lock()
	defer w.statsLock.Unlock()

	updateFunc(w.currentStats)
}
