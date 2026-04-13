package worker

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
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

// Start dispatches to the correct mode and blocks until done or signalled.
func (w *Worker) Start(quit <-chan os.Signal) {
	switch w.cfg.Agent.Mode {
	case "historical":
		// Downloads to disk — no InsightFinder connection needed.
		w.runHistoricalDownload(quit)
		return
	}

	// All remaining modes need InsightFinder.
	if err := w.ifSvc.Initialize(); err != nil {
		logrus.Errorf("Failed to initialize InsightFinder: %v", err)
		return
	}

	w.runContinuous(quit)
}

// runContinuous polls Splunk every sampling_interval and forwards results to InsightFinder.
func (w *Worker) runContinuous(quit <-chan os.Signal) {
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

// ─── historical download mode ───────────────────────────────────────────────

// runHistoricalDownload queries Splunk for start_time→end_time and writes the
// InsightFinder-ready log entries to JSONL files under download_path.
// One file is created per enabled query:
//
//	{download_path}/{query_name}_{startUnix}_{endUnix}.jsonl
//
// Each line is a JSON-encoded insightfinder.LogData object.
func (w *Worker) runHistoricalDownload(quit <-chan os.Signal) {
	start, end, ok := w.parseHistoricalRange()
	if !ok {
		return
	}

	downloadPath := w.cfg.Agent.DownloadPath
	if err := os.MkdirAll(downloadPath, 0755); err != nil {
		logrus.Errorf("Cannot create download_path '%s': %v", downloadPath, err)
		return
	}

	chunkSize := time.Duration(w.cfg.Agent.ChunkInterval) * time.Minute

	totalDuration := end.Sub(start)
	totalChunks := int(totalDuration / chunkSize)
	if totalDuration%chunkSize != 0 {
		totalChunks++
	}

	logrus.Infof("Historical download started")
	logrus.Infof("  Range:       %s → %s", start.Format(time.RFC3339), end.Format(time.RFC3339))
	logrus.Infof("  Chunk size:  %d min", w.cfg.Agent.ChunkInterval)
	logrus.Infof("  Total chunks: %d", totalChunks)
	logrus.Infof("  Destination: %s", downloadPath)

	// Open one output file per enabled query.
	type queryFile struct {
		cfg    configs.QueryConfig
		writer *bufio.Writer
		file   *os.File
		count  int
	}
	files := make(map[string]*queryFile)
	defer func() {
		logrus.Info("── Download summary ──────────────────────────────")
		for _, qf := range files {
			qf.writer.Flush()
			qf.file.Close()
			logrus.Infof("  %-20s  %6d events  →  %s", qf.cfg.Name, qf.count, qf.file.Name())
		}
		logrus.Info("─────────────────────────────────────────────────")
	}()

	for _, qCfg := range w.cfg.Splunk.Queries {
		if !qCfg.Enabled {
			continue
		}
		fname := fmt.Sprintf("%s_%d_%d.jsonl",
			sanitizeFilename(qCfg.Name), start.Unix(), end.Unix())
		fpath := filepath.Join(downloadPath, fname)
		f, err := os.Create(fpath)
		if err != nil {
			logrus.Errorf("Cannot create file %s: %v", fpath, err)
			continue
		}
		logrus.Infof("Output file: %s", fpath)
		files[qCfg.Name] = &queryFile{cfg: qCfg, writer: bufio.NewWriter(f), file: f}
	}

	// Walk the time range in chunk-sized steps.
	chunkNum := 0
	for current := start; current.Before(end); {
		select {
		case <-quit:
			logrus.Info("Historical download interrupted")
			return
		default:
		}

		chunkEnd := current.Add(chunkSize)
		if chunkEnd.After(end) {
			chunkEnd = end
		}
		chunkNum++
		pct := float64(chunkNum) / float64(totalChunks) * 100
		logrus.Infof("[%d/%d] (%.1f%%)  %s → %s",
			chunkNum, totalChunks, pct,
			current.Format("2006-01-02 15:04"), chunkEnd.Format("2006-01-02 15:04"))

		for name, qf := range files {
			events, err := w.splunkSvc.SearchRange(qf.cfg, current, chunkEnd)
			if err != nil {
				logrus.Errorf("  Query '%s' failed: %v", name, err)
				continue
			}

			slim := convertEvents(events)
			logDataList := w.ifSvc.ConvertToLogData(slim, qf.cfg)

			for _, ld := range logDataList {
				line, err := json.Marshal(ld)
				if err != nil {
					logrus.Warnf("Failed to marshal log entry: %v", err)
					continue
				}
				qf.writer.Write(line)
				qf.writer.WriteByte('\n')
				qf.count++
			}
			logrus.Infof("  %-20s  %d events (total: %d)", name, len(logDataList), qf.count)
		}

		current = chunkEnd
	}

	logrus.Infof("Historical download complete. Files in: %s", downloadPath)
}

// ─── time range helpers ──────────────────────────────────────────────────────

func (w *Worker) parseHistoricalRange() (start, end time.Time, ok bool) {
	var err error
	start, err = configs.ParseAgentTime(w.cfg.Agent.StartTime)
	if err != nil {
		logrus.Errorf("Invalid start_time: %v", err)
		return
	}
	if w.cfg.Agent.EndTime != "" {
		end, err = configs.ParseAgentTime(w.cfg.Agent.EndTime)
		if err != nil {
			logrus.Errorf("Invalid end_time: %v", err)
			return
		}
	} else {
		end = time.Now()
	}
	if !start.Before(end) {
		logrus.Errorf("start_time (%s) must be before end_time (%s)",
			start.Format(time.RFC3339), end.Format(time.RFC3339))
		return
	}
	ok = true
	return
}

// ─── file utilities ──────────────────────────────────────────────────────────

// sanitizeFilename replaces characters that are invalid in filenames with underscores.
func sanitizeFilename(name string) string {
	result := make([]byte, len(name))
	for i := 0; i < len(name); i++ {
		c := name[i]
		if c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|' {
			result[i] = '_'
		} else {
			result[i] = c
		}
	}
	return string(result)
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
