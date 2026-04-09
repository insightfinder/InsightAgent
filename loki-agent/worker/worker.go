package worker

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sync"
	"time"

	config "github.com/insightfinder/loki-agent/configs"
	"github.com/insightfinder/loki-agent/insightfinder"
	"github.com/insightfinder/loki-agent/loki"
	"github.com/insightfinder/loki-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// compiledFilter holds a pre-compiled regex and its replacement string.
type compiledFilter struct {
	re          *regexp.Regexp
	replacement string
}

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

	// Pre-compiled sensitive data filters keyed by query name
	filterCacheMu sync.RWMutex
	filterCache   map[string][]compiledFilter
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
		filterCache:    make(map[string][]compiledFilter),
	}
}

// Start dispatches to the correct mode.
func (w *Worker) Start(quit <-chan os.Signal) {
	switch w.config.Agent.Mode {
	case "historical":
		// Downloads to disk — no InsightFinder connection needed.
		w.runHistoricalDownload(quit)
		return
	case "replay":
		// Reads from disk and sends to InsightFinder.
		if err := w.insightFinderService.Initialize(); err != nil {
			logrus.Errorf("Failed to initialize InsightFinder service: %v", err)
			return
		}
		w.runReplay(quit)
		return
	}

	// All remaining modes need InsightFinder.
	if err := w.insightFinderService.Initialize(); err != nil {
		logrus.Errorf("Failed to initialize InsightFinder service: %v", err)
		return
	}
	logrus.Info("InsightFinder service initialized successfully")

	switch w.config.Agent.Mode {
	case "stream_historical":
		w.runHistoricalStream(quit)
	default:
		w.runContinuous(quit)
	}
}

// ─── continuous mode ────────────────────────────────────────────────────────

func (w *Worker) runContinuous(quit <-chan os.Signal) {
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	ticker := time.NewTicker(samplingInterval)
	defer ticker.Stop()

	logrus.Infof("Worker started in continuous mode. Collection interval: %d seconds",
		w.config.InsightFinder.SamplingInterval)

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

// ─── historical download mode ───────────────────────────────────────────────

// runHistoricalDownload queries Loki for start_time→end_time and writes the
// InsightFinder-ready log entries to NDJSON files under download_path.
// One file is created per enabled query:
//
//	{download_path}/{query_name}_{startUnix}_{endUnix}.ndjson
//
// Each line is a JSON-encoded insightfinder.LogData object.
func (w *Worker) runHistoricalDownload(quit <-chan os.Signal) {
	start, end, ok := w.parseHistoricalRange()
	if !ok {
		return
	}

	downloadPath := w.config.Agent.DownloadPath
	if err := os.MkdirAll(downloadPath, 0755); err != nil {
		logrus.Errorf("Cannot create download_path '%s': %v", downloadPath, err)
		return
	}

	chunkSize := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	logrus.Infof("Historical download: %s → %s  (chunk %s, dest: %s)",
		start.Format(time.RFC3339), end.Format(time.RFC3339), chunkSize, downloadPath)

	// Open one output file per enabled query.
	type queryFile struct {
		cfg    config.QueryConfig
		writer *bufio.Writer
		file   *os.File
		count  int
	}
	files := make(map[string]*queryFile)
	defer func() {
		for _, qf := range files {
			qf.writer.Flush()
			qf.file.Close()
			logrus.Infof("Saved %d entries → %s", qf.count, qf.file.Name())
		}
	}()

	for _, qCfg := range w.config.Loki.Queries {
		if !qCfg.Enabled {
			continue
		}
		fname := fmt.Sprintf("%s_%d_%d.ndjson",
			sanitizeFilename(qCfg.Name), start.Unix(), end.Unix())
		fpath := filepath.Join(downloadPath, fname)
		f, err := os.Create(fpath)
		if err != nil {
			logrus.Errorf("Cannot create file %s: %v", fpath, err)
			continue
		}
		files[qCfg.Name] = &queryFile{cfg: qCfg, writer: bufio.NewWriter(f), file: f}
	}

	// Walk the time range in sampling_interval-sized chunks.
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

		for name, qf := range files {
			entries, err := w.fetchEntries(qf.cfg, current, chunkEnd)
			if err != nil {
				logrus.Errorf("Query '%s' failed for chunk %s→%s: %v",
					name, current.Format(time.RFC3339), chunkEnd.Format(time.RFC3339), err)
				continue
			}

			entries = w.applySensitiveFilters(entries, qf.cfg)
			logDataList := w.insightFinderService.ConvertToLogData(entries, qf.cfg)

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
		}

		current = chunkEnd
	}

	logrus.Infof("Historical download complete. Files in: %s", downloadPath)
}

// ─── replay mode (the "client") ─────────────────────────────────────────────

// runReplay reads NDJSON files produced by historical-download mode and
// streams each LogData entry to InsightFinder.
// replay_path may be a single .ndjson file or a directory (all *.ndjson replayed in order).
func (w *Worker) runReplay(quit <-chan os.Signal) {
	replayPath := w.config.Agent.ReplayPath

	files, err := resolveNDJSONPaths(replayPath)
	if err != nil {
		logrus.Errorf("replay_path error: %v", err)
		return
	}
	if len(files) == 0 {
		logrus.Warnf("No NDJSON files found at replay_path '%s'", replayPath)
		return
	}

	logrus.Infof("Replay mode: streaming %d file(s) to InsightFinder", len(files))

	chunkWait := time.Duration(w.config.Agent.StreamChunkInterval) * time.Second
	batchSize := 1000 // entries per send call

	for _, fpath := range files {
		select {
		case <-quit:
			logrus.Info("Replay interrupted")
			return
		default:
		}

		if err := w.replayFile(fpath, batchSize, chunkWait, quit); err != nil {
			logrus.Errorf("Error replaying %s: %v", fpath, err)
		}
	}

	logrus.Info("Replay complete")
}

// replayFile streams a single NDJSON file to InsightFinder in batches.
func (w *Worker) replayFile(path string, batchSize int, chunkWait time.Duration, quit <-chan os.Signal) error {
	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("cannot open file: %v", err)
	}
	defer f.Close()

	logrus.Infof("Replaying: %s", path)

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 4*1024*1024), 4*1024*1024) // 4 MB line buffer
	var batch []insightfinder.LogData
	total := 0

	flush := func() {
		if len(batch) == 0 {
			return
		}
		if !w.testMode {
			if err := w.insightFinderService.SendLogDataInternal(batch); err != nil {
				logrus.Errorf("Failed to send batch: %v", err)
			}
		} else {
			logrus.Infof("TEST MODE: Would send %d entries", len(batch))
		}
		total += len(batch)
		batch = batch[:0]
	}

	for scanner.Scan() {
		select {
		case <-quit:
			flush()
			return nil
		default:
		}

		var entry insightfinder.LogData
		if err := json.Unmarshal(scanner.Bytes(), &entry); err != nil {
			logrus.Warnf("Skipping invalid line in %s: %v", path, err)
			continue
		}
		batch = append(batch, entry)

		if len(batch) >= batchSize {
			flush()
			if chunkWait > 0 {
				select {
				case <-quit:
					return nil
				case <-time.After(chunkWait):
				}
			}
		}
	}

	flush()
	logrus.Infof("Replayed %d entries from %s", total, path)
	return scanner.Err()
}

// ─── stream_historical mode ──────────────────────────────────────────────────

// runHistoricalStream walks start_time→end_time in sampling_interval chunks,
// streaming directly to InsightFinder (no files written).
func (w *Worker) runHistoricalStream(quit <-chan os.Signal) {
	start, end, ok := w.parseHistoricalRange()
	if !ok {
		return
	}

	chunkSize := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	chunkWait := time.Duration(w.config.Agent.StreamChunkInterval) * time.Second

	logrus.Infof("Historical stream: %s → %s  (chunk %s, wait %s)",
		start.Format(time.RFC3339), end.Format(time.RFC3339), chunkSize, chunkWait)

	total := 0
	for current := start; current.Before(end); {
		select {
		case <-quit:
			logrus.Info("Historical stream interrupted")
			return
		default:
		}

		chunkEnd := current.Add(chunkSize)
		if chunkEnd.After(end) {
			chunkEnd = end
		}

		n, _ := w.processAllQueriesForRange(current, chunkEnd)
		total += n
		current = chunkEnd

		if chunkWait > 0 && current.Before(end) {
			select {
			case <-quit:
				return
			case <-time.After(chunkWait):
			}
		}
	}

	logrus.Infof("Historical stream complete. Total entries sent: %d", total)
}

// ─── shared query helpers ────────────────────────────────────────────────────

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
			w.incrementErrorCount()
		}
	}
}

func (w *Worker) processAllQueriesForRange(start, end time.Time) (int, error) {
	w.updateStats(func(stats *models.CollectionStats) {
		stats.LastUpdateTime = time.Now()
	})
	total := 0
	for _, queryConfig := range w.config.Loki.Queries {
		if !queryConfig.Enabled {
			continue
		}
		n, err := w.processQueryForRange(queryConfig, start, end)
		if err != nil {
			logrus.Errorf("Error processing query '%s': %v", queryConfig.Name, err)
			w.incrementErrorCount()
		}
		total += n
	}
	return total, nil
}

// processQuery uses the rolling sampling-interval window (continuous mode).
func (w *Worker) processQuery(queryConfig config.QueryConfig) error {
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	end := time.Now()
	start := end.Add(-samplingInterval)

	if last := w.getLastQueryTime(queryConfig.Name); last != nil && last.After(start) {
		start = *last
	}
	if !start.Before(end) {
		return nil
	}

	if _, err := w.processQueryForRange(queryConfig, start, end); err != nil {
		return err
	}
	w.updateLastQueryTime(queryConfig.Name, end)
	return nil
}

// processQueryForRange fetches, filters, and sends entries for an explicit time range.
func (w *Worker) processQueryForRange(queryConfig config.QueryConfig, start, end time.Time) (int, error) {
	queryStartTime := time.Now()

	logrus.Infof("Querying '%s' from %s to %s",
		queryConfig.Name, start.Format(time.RFC3339), end.Format(time.RFC3339))

	entries, err := w.fetchEntries(queryConfig, start, end)
	if err != nil {
		return 0, err
	}

	entries = w.applySensitiveFilters(entries, queryConfig)

	if len(entries) == 0 {
		logrus.Infof("No log entries for query '%s'", queryConfig.Name)
		return 0, nil
	}

	logrus.Infof("Found %d entries for query '%s'", len(entries), queryConfig.Name)

	if !w.testMode {
		result, err := w.insightFinderService.SendLogData(entries, queryConfig)
		if err != nil {
			return 0, fmt.Errorf("failed to send data to InsightFinder: %v", err)
		}
		logrus.Infof("Sent %d entries (%d bytes) in %v",
			result.EntriesSent, result.BytesSent, result.TimeTaken)
	} else {
		logrus.Infof("TEST MODE: Would send %d entries", len(entries))
	}

	dur := time.Since(queryStartTime)
	w.updateStats(func(stats *models.CollectionStats) {
		stats.TotalQueries++
		stats.TotalLogEntries += len(entries)
		stats.ProcessedEntries += len(entries)
		stats.LastSuccessfulQuery = time.Now()
		if stats.TotalQueries == 1 {
			stats.AverageQueryTime = dur
		} else {
			stats.AverageQueryTime = (stats.AverageQueryTime + dur) / 2
		}
		if elapsed := time.Since(stats.StartTime).Minutes(); elapsed > 0 {
			stats.QueriesPerMinute = float64(stats.TotalQueries) / elapsed
		}
	})

	return len(entries), nil
}

// fetchEntries queries Loki for a single query config over the given range.
func (w *Worker) fetchEntries(queryConfig config.QueryConfig, start, end time.Time) ([]models.LogEntry, error) {
	response, err := w.lokiService.QueryRange(loki.QueryRequest{
		Query:     queryConfig.Query,
		Start:     start,
		End:       end,
		Limit:     queryConfig.MaxEntries,
		Direction: "forward",
		Labels:    queryConfig.Labels,
	})
	if err != nil {
		return nil, fmt.Errorf("Loki query failed: %v", err)
	}

	entries, err := w.lokiService.ConvertResponseToLogEntries(response, queryConfig.Labels)
	if err != nil {
		return nil, fmt.Errorf("failed to convert response: %v", err)
	}
	return entries, nil
}

// ─── sensitive data filtering ────────────────────────────────────────────────

func (w *Worker) getCompiledFilters(queryConfig config.QueryConfig) []compiledFilter {
	w.filterCacheMu.RLock()
	if filters, ok := w.filterCache[queryConfig.Name]; ok {
		w.filterCacheMu.RUnlock()
		return filters
	}
	w.filterCacheMu.RUnlock()

	var filters []compiledFilter
	for _, f := range queryConfig.SensitiveDataFilters {
		re, err := regexp.Compile(f.Regex)
		if err != nil {
			logrus.Warnf("Query '%s': skipping invalid regex '%s': %v", queryConfig.Name, f.Regex, err)
			continue
		}
		filters = append(filters, compiledFilter{re: re, replacement: f.Replacement})
	}

	w.filterCacheMu.Lock()
	w.filterCache[queryConfig.Name] = filters
	w.filterCacheMu.Unlock()
	return filters
}

func (w *Worker) applySensitiveFilters(entries []models.LogEntry, queryConfig config.QueryConfig) []models.LogEntry {
	if len(queryConfig.SensitiveDataFilters) == 0 {
		return entries
	}
	filters := w.getCompiledFilters(queryConfig)
	if len(filters) == 0 {
		return entries
	}
	for i := range entries {
		for _, f := range filters {
			entries[i].Message = f.re.ReplaceAllString(entries[i].Message, f.replacement)
		}
	}
	return entries
}

// ─── time range helpers ──────────────────────────────────────────────────────

func (w *Worker) parseHistoricalRange() (start, end time.Time, ok bool) {
	var err error
	start, err = config.ParseAgentTime(w.config.Agent.StartTime)
	if err != nil {
		logrus.Errorf("Invalid start_time: %v", err)
		return
	}
	if w.config.Agent.EndTime != "" {
		end, err = config.ParseAgentTime(w.config.Agent.EndTime)
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

// resolveNDJSONPaths returns a sorted list of .ndjson file paths.
// If path is a directory, all *.ndjson files inside are returned.
// If path is a file, that single file is returned.
func resolveNDJSONPaths(path string) ([]string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("cannot stat '%s': %v", path, err)
	}
	if !info.IsDir() {
		return []string{path}, nil
	}
	matches, err := filepath.Glob(filepath.Join(path, "*.ndjson"))
	if err != nil {
		return nil, err
	}
	return matches, nil
}

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

// ─── misc helpers ────────────────────────────────────────────────────────────

func (w *Worker) EnableTestMode() {
	w.testMode = true
	logrus.Info("Test mode enabled - data will not be sent to InsightFinder")
}

func (w *Worker) GetStats() models.CollectionStats {
	w.statsLock.RLock()
	defer w.statsLock.RUnlock()
	return *w.currentStats
}

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

func (w *Worker) incrementErrorCount() {
	w.updateStats(func(stats *models.CollectionStats) {
		stats.ErrorCount++
	})
}

func (w *Worker) updateStats(updateFunc func(*models.CollectionStats)) {
	w.statsLock.Lock()
	defer w.statsLock.Unlock()
	updateFunc(w.currentStats)
}
