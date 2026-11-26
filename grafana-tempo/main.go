package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

const traceLookupPadding = time.Hour

type windowStats struct {
	found   atomic.Int64
	skipped atomic.Int64
	sent    atomic.Int64
	spans   atomic.Int64
	missing atomic.Int64
	failed  atomic.Int64
}

type Agent struct {
	cfg    *Config
	tempo  *TempoClient
	sender *TraceSender
	seen   *seenCache
}

func main() {
	configPath := flag.String("c", "config.yaml", "config file path")
	flag.Parse()

	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

	cfg, err := LoadConfig(*configPath)
	if err != nil {
		slog.Error("load config", "error", err)
		os.Exit(1)
	}

	agent := &Agent{
		cfg:   cfg,
		tempo: NewTempoClient(cfg.Tempo),
		seen:  newSeenCache(),
	}
	if !cfg.InsightFinder.DryRun {
		agent.sender, err = NewTraceSender(cfg.InsightFinder)
		if err != nil {
			slog.Error("create trace sender", "error", err)
			os.Exit(1)
		}
		defer agent.sender.Close()
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := agent.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		slog.Error("agent stopped", "error", err)
		os.Exit(1)
	}
	slog.Info("agent stopped")
}

func (a *Agent) Run(ctx context.Context) error {
	interval := a.cfg.Agent.Interval.Duration
	delay := a.cfg.Agent.Delay.Duration

	next := a.resumePoint()
	slog.Info("agent started",
		"tempo", a.cfg.Tempo.Endpoint,
		"query", a.cfg.Tempo.Query,
		"trace_server", a.cfg.InsightFinder.TraceServer,
		"project", a.cfg.InsightFinder.ProjectName,
		"dry_run", a.cfg.InsightFinder.DryRun,
		"from", next.Format(time.RFC3339),
		"interval", interval,
		"delay", delay,
	)

	for {
		if !a.cfg.endTime.IsZero() && !next.Before(a.cfg.endTime) {
			slog.Info("reached end_time", "end_time", a.cfg.endTime.Format(time.RFC3339))
			return nil
		}
		windowEnd := next.Add(interval)
		if !a.cfg.endTime.IsZero() && windowEnd.After(a.cfg.endTime) {
			windowEnd = a.cfg.endTime
		}

		readyAt := windowEnd.Add(delay)
		if wait := time.Until(readyAt); wait > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(wait):
			}
		}

		if err := a.processWindow(ctx, next, windowEnd); err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			slog.Error("window failed, will retry", "start", next.Format(time.RFC3339), "end", windowEnd.Format(time.RFC3339), "error", err)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(15 * time.Second):
			}
			continue
		}

		a.saveState(windowEnd)
		a.seen.expire(windowEnd.Add(-10 * interval))
		next = windowEnd
	}
}

func (a *Agent) resumePoint() time.Time {
	if t, ok := loadState(a.cfg.Agent.StateFile); ok {
		slog.Info("resuming from state file", "state_file", a.cfg.Agent.StateFile, "from", t.Format(time.RFC3339))
		return t
	}
	if !a.cfg.startTime.IsZero() {
		return a.cfg.startTime
	}
	return time.Now().Add(-a.cfg.Agent.Delay.Duration - a.cfg.Agent.Interval.Duration).Truncate(time.Second)
}

func (a *Agent) saveState(t time.Time) {
	if err := saveState(a.cfg.Agent.StateFile, t); err != nil {
		slog.Warn("save state", "state_file", a.cfg.Agent.StateFile, "error", err)
	}
}

func (a *Agent) processWindow(ctx context.Context, start, end time.Time) error {
	traces, err := a.searchAll(ctx, start, end)
	if err != nil {
		return err
	}

	stats := &windowStats{}
	stats.found.Store(int64(len(traces)))

	jobs := make(chan SearchTrace)
	var wg sync.WaitGroup
	for i := 0; i < a.cfg.Agent.Workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for t := range jobs {
				a.handleTrace(ctx, t, start, end, stats)
			}
		}()
	}
	for _, t := range traces {
		id := normalizeTraceID(t.TraceID)
		if !a.seen.add(id, end) {
			stats.skipped.Add(1)
			continue
		}
		t.TraceID = id
		select {
		case jobs <- t:
		case <-ctx.Done():
		}
	}
	close(jobs)
	wg.Wait()

	slog.Info("window done",
		"start", start.Format(time.RFC3339),
		"end", end.Format(time.RFC3339),
		"found", stats.found.Load(),
		"duplicates", stats.skipped.Load(),
		"sent", stats.sent.Load(),
		"spans", stats.spans.Load(),
		"not_found", stats.missing.Load(),
		"failed", stats.failed.Load(),
	)
	return ctx.Err()
}

func (a *Agent) searchAll(ctx context.Context, start, end time.Time) ([]SearchTrace, error) {
	traces, err := a.tempo.Search(ctx, start, end)
	if err != nil {
		return nil, err
	}
	if len(traces) < a.cfg.Tempo.Limit || end.Sub(start) <= time.Second {
		if len(traces) >= a.cfg.Tempo.Limit {
			slog.Warn("search hit the limit in a 1s window, some traces may be skipped; raise tempo.limit",
				"start", start.Format(time.RFC3339), "limit", a.cfg.Tempo.Limit)
		}
		return traces, nil
	}
	mid := start.Add(end.Sub(start) / 2).Truncate(time.Second)
	if !mid.After(start) {
		mid = start.Add(time.Second)
	}
	slog.Info("search hit the limit, splitting window", "start", start.Format(time.RFC3339), "end", end.Format(time.RFC3339), "limit", a.cfg.Tempo.Limit)
	left, err := a.searchAll(ctx, start, mid)
	if err != nil {
		return nil, err
	}
	right, err := a.searchAll(ctx, mid, end)
	if err != nil {
		return nil, err
	}
	return append(left, right...), nil
}

func (a *Agent) handleTrace(ctx context.Context, t SearchTrace, start, end time.Time, stats *windowStats) {
	td, err := a.tempo.GetTrace(ctx, t.TraceID, start.Add(-traceLookupPadding), end.Add(traceLookupPadding))
	if err != nil {
		stats.failed.Add(1)
		slog.Warn("fetch trace", "trace_id", t.TraceID, "error", err)
		return
	}
	spanCount := countSpans(td)
	if td == nil || spanCount == 0 {
		stats.missing.Add(1)
		slog.Warn("trace has no spans", "trace_id", t.TraceID)
		return
	}

	if a.sender == nil {
		slog.Info("dry run", "trace_id", t.TraceID, "root_service", t.RootServiceName, "root_name", t.RootTraceName,
			"spans", spanCount, "services", strings.Join(serviceNames(td), ","))
	} else if err := a.sender.Send(ctx, td); err != nil {
		stats.failed.Add(1)
		slog.Warn("send trace", "trace_id", t.TraceID, "error", err)
		return
	} else {
		slog.Debug("sent trace", "trace_id", t.TraceID, "spans", spanCount)
	}
	stats.sent.Add(1)
	stats.spans.Add(int64(spanCount))
}

func countSpans(td *tracepb.TracesData) int {
	if td == nil {
		return 0
	}
	n := 0
	for _, rs := range td.ResourceSpans {
		for _, ss := range rs.ScopeSpans {
			n += len(ss.Spans)
		}
	}
	return n
}

func serviceNames(td *tracepb.TracesData) []string {
	set := map[string]struct{}{}
	names := []string{}
	for _, rs := range td.ResourceSpans {
		for _, kv := range rs.GetResource().GetAttributes() {
			if kv.Key == "service.name" {
				name := kv.GetValue().GetStringValue()
				if _, ok := set[name]; !ok {
					set[name] = struct{}{}
					names = append(names, name)
				}
			}
		}
	}
	return names
}

func normalizeTraceID(id string) string {
	id = strings.ToLower(strings.TrimSpace(id))
	if len(id) < 32 {
		id = strings.Repeat("0", 32-len(id)) + id
	}
	return id
}

type seenCache struct {
	mu    sync.Mutex
	items map[string]time.Time
}

func newSeenCache() *seenCache {
	return &seenCache{items: map[string]time.Time{}}
}

func (c *seenCache) add(id string, windowEnd time.Time) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	if _, ok := c.items[id]; ok {
		return false
	}
	c.items[id] = windowEnd
	return true
}

func (c *seenCache) expire(before time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for id, t := range c.items {
		if t.Before(before) {
			delete(c.items, id)
		}
	}
}

func loadState(path string) (time.Time, bool) {
	if path == "" {
		return time.Time{}, false
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return time.Time{}, false
	}
	t, err := time.Parse(time.RFC3339, strings.TrimSpace(string(raw)))
	if err != nil {
		slog.Warn("ignore invalid state file", "state_file", path, "error", err)
		return time.Time{}, false
	}
	return t, true
}

func saveState(path string, t time.Time) error {
	if path == "" {
		return nil
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, []byte(t.UTC().Format(time.RFC3339)+"\n"), 0o644); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return fmt.Errorf("rename state file: %w", err)
	}
	return nil
}
