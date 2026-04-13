package worker

import (
	"os"
	"sync"
	"time"

	"github.com/insightfinder/splunk-agent/configs"
	"github.com/insightfinder/splunk-agent/insightfinder"
	"github.com/insightfinder/splunk-agent/splunk"
	"github.com/sirupsen/logrus"
)

// Worker orchestrates polling Splunk and forwarding events to InsightFinder.
type Worker struct {
	cfg       *configs.Config
	splunkSvc *splunk.Service
	ifSvc     *insightfinder.Service

	// lastQueryTime tracks the end of the last successful window per query,
	// so the next poll starts exactly where the previous one ended.
	lastQueryTime map[string]time.Time
	mu            sync.Mutex
}

// New creates a Worker.
func New(cfg *configs.Config, splunkSvc *splunk.Service, ifSvc *insightfinder.Service) *Worker {
	return &Worker{
		cfg:           cfg,
		splunkSvc:     splunkSvc,
		ifSvc:         ifSvc,
		lastQueryTime: make(map[string]time.Time),
	}
}

// Start runs in continuous mode: poll every sampling_interval, forward results,
// and block until a signal is received on quit.
func (w *Worker) Start(quit <-chan os.Signal) {
	if err := w.ifSvc.Initialize(); err != nil {
		logrus.Errorf("Failed to initialize InsightFinder: %v", err)
		return
	}

	interval := time.Duration(w.cfg.InsightFinder.SamplingInterval) * time.Second
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	logrus.Infof("Worker started in continuous mode (interval: %s)", interval)
	if w.cfg.Splunk.ConcurrentQueries {
		max := w.cfg.Splunk.MaxConcurrent
		if max <= 0 {
			logrus.Info("Concurrent query mode: all queries run in parallel")
		} else {
			logrus.Infof("Concurrent query mode: up to %d queries at a time", max)
		}
	} else {
		logrus.Info("Sequential query mode")
	}

	// Run once immediately on startup, then on every tick.
	w.processAll()

	for {
		select {
		case <-quit:
			logrus.Info("Worker received shutdown signal, stopping")
			return
		case <-ticker.C:
			w.processAll()
		}
	}
}

// processAll runs every enabled query, either sequentially or concurrently
// depending on the splunk.concurrent_queries configuration.
func (w *Worker) processAll() {
	enabled := make([]configs.QueryConfig, 0)
	for _, q := range w.cfg.Splunk.Queries {
		if q.Enabled {
			enabled = append(enabled, q)
		}
	}

	if !w.cfg.Splunk.ConcurrentQueries {
		// Sequential (default) — same behaviour as before.
		for _, q := range enabled {
			if err := w.processQuery(q); err != nil {
				logrus.Errorf("Query '%s' error: %v", q.Name, err)
			}
		}
		return
	}

	// Concurrent — run queries in parallel with an optional concurrency cap.
	maxConcurrent := w.cfg.Splunk.MaxConcurrent
	if maxConcurrent <= 0 {
		maxConcurrent = len(enabled)
	}

	sem := make(chan struct{}, maxConcurrent)
	var wg sync.WaitGroup

	for _, q := range enabled {
		wg.Add(1)
		sem <- struct{}{}
		go func(q configs.QueryConfig) {
			defer wg.Done()
			defer func() { <-sem }()
			if err := w.processQuery(q); err != nil {
				logrus.Errorf("Query '%s' error: %v", q.Name, err)
			}
		}(q)
	}
	wg.Wait()
}

// processQuery determines the time window, fetches from Splunk, and sends to IF.
func (w *Worker) processQuery(q configs.QueryConfig) error {
	now := time.Now()
	interval := time.Duration(w.cfg.InsightFinder.SamplingInterval) * time.Second

	w.mu.Lock()
	start, ok := w.lastQueryTime[q.Name]
	if !ok {
		// First run: look back one full interval.
		start = now.Add(-interval)
	}
	w.mu.Unlock()

	if !start.Before(now) {
		logrus.Debugf("Query '%s': no new window, skipping", q.Name)
		return nil
	}

	logrus.Infof("Query '%s': fetching %s → %s", q.Name,
		start.Format(time.RFC3339), now.Format(time.RFC3339))

	events, err := w.splunkSvc.SearchRange(q, start, now)
	if err != nil {
		return err
	}

	logrus.Infof("Query '%s': got %d events", q.Name, len(events))

	if len(events) > 0 {
		slim := convertEvents(events)
		if err := w.ifSvc.SendLogData(slim, q); err != nil {
			return err
		}
	}

	// Advance the window only on success.
	w.mu.Lock()
	w.lastQueryTime[q.Name] = now
	w.mu.Unlock()

	return nil
}

// convertEvents maps []splunk.SplunkEvent → []insightfinder.SplunkEventSlim.
// All Splunk fields are preserved in SplunkEventSlim.Fields so they can be
// forwarded as structured JSON and used for dynamic tag/component resolution.
func convertEvents(events []splunk.SplunkEvent) []insightfinder.SplunkEventSlim {
	out := make([]insightfinder.SplunkEventSlim, 0, len(events))
	for _, e := range events {
		out = append(out, insightfinder.SplunkEventSlim{
			TimestampMs: splunk.ParseTimestamp(e.GetString("_time")),
			Fields:      map[string]interface{}(e),
		})
	}
	return out
}
