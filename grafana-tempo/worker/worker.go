package worker

import (
	"context"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	config "github.com/insightfinder/grafana-tempo-agent/configs"
	"github.com/insightfinder/grafana-tempo-agent/insightfinder"
	"github.com/insightfinder/grafana-tempo-agent/tempo"
	"github.com/sirupsen/logrus"
)

const (
	traceLookupPadding = time.Hour
	retryWait          = 15 * time.Second
	seenWindows        = 10
)

type windowStats struct {
	found      atomic.Int64
	duplicates atomic.Int64
	sent       atomic.Int64
	spans      atomic.Int64
	notFound   atomic.Int64
	failed     atomic.Int64
}

type Worker struct {
	config       *config.Config
	tempoService *tempo.Service
	ifService    *insightfinder.Service
	seen         *seenCache
}

func NewWorker(cfg *config.Config, tempoService *tempo.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:       cfg,
		tempoService: tempoService,
		ifService:    ifService,
		seen:         newSeenCache(),
	}
}

func (w *Worker) Start(ctx context.Context) error {
	interval := w.config.Agent.Interval.Duration
	delay := w.config.Agent.Delay.Duration
	end := w.config.Agent.End

	next := w.resumePoint()
	logrus.Infof("Streaming traces from %s, window %s, delay %s", next.Format(time.RFC3339), interval, delay)

	for {
		if !end.IsZero() && !next.Before(end) {
			logrus.Infof("Reached end_time %s", end.Format(time.RFC3339))
			return nil
		}
		windowEnd := next.Add(interval)
		if !end.IsZero() && windowEnd.After(end) {
			windowEnd = end
		}

		if wait := time.Until(windowEnd.Add(delay)); wait > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(wait):
			}
		}

		if err := w.processWindow(ctx, next, windowEnd); err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			logrus.Errorf("Window %s - %s failed, retrying in %s: %v",
				next.Format(time.RFC3339), windowEnd.Format(time.RFC3339), retryWait, err)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(retryWait):
			}
			continue
		}

		if err := saveState(w.config.Agent.StateFile, windowEnd); err != nil {
			logrus.Warnf("Failed to save state file %s: %v", w.config.Agent.StateFile, err)
		}
		w.seen.expire(windowEnd.Add(-seenWindows * interval))
		next = windowEnd
	}
}

func (w *Worker) resumePoint() time.Time {
	if t, ok := loadState(w.config.Agent.StateFile); ok {
		logrus.Infof("Resuming from state file %s", w.config.Agent.StateFile)
		return t
	}
	if !w.config.Agent.Start.IsZero() {
		return w.config.Agent.Start
	}
	return time.Now().Add(-w.config.Agent.Delay.Duration - w.config.Agent.Interval.Duration).Truncate(time.Second)
}

func (w *Worker) processWindow(ctx context.Context, start, end time.Time) error {
	traces, err := w.searchAll(ctx, start, end)
	if err != nil {
		return err
	}

	stats := &windowStats{}
	stats.found.Store(int64(len(traces)))

	jobs := make(chan tempo.SearchTrace)
	var wg sync.WaitGroup
	for i := 0; i < w.config.Agent.Workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for t := range jobs {
				w.processTrace(ctx, t, start, end, stats)
			}
		}()
	}
	for _, t := range traces {
		t.TraceID = normalizeTraceID(t.TraceID)
		if !w.seen.add(t.TraceID, end) {
			stats.duplicates.Add(1)
			continue
		}
		select {
		case jobs <- t:
		case <-ctx.Done():
		}
	}
	close(jobs)
	wg.Wait()

	logrus.Infof("Window %s - %s: found=%d duplicates=%d sent=%d spans=%d not_found=%d failed=%d",
		start.Format(time.RFC3339), end.Format(time.RFC3339),
		stats.found.Load(), stats.duplicates.Load(), stats.sent.Load(),
		stats.spans.Load(), stats.notFound.Load(), stats.failed.Load())
	return ctx.Err()
}

func (w *Worker) searchAll(ctx context.Context, start, end time.Time) ([]tempo.SearchTrace, error) {
	traces, err := w.tempoService.Search(ctx, start, end)
	if err != nil {
		return nil, err
	}
	limit := w.config.Tempo.Limit
	if len(traces) < limit {
		return traces, nil
	}
	if end.Sub(start) <= time.Second {
		logrus.Warnf("Search hit the limit %d in a 1s window at %s, some traces may be skipped; raise tempo.limit",
			limit, start.Format(time.RFC3339))
		return traces, nil
	}

	mid := start.Add(end.Sub(start) / 2).Truncate(time.Second)
	if !mid.After(start) {
		mid = start.Add(time.Second)
	}
	logrus.Debugf("Search hit the limit %d for %s - %s, splitting the window",
		limit, start.Format(time.RFC3339), end.Format(time.RFC3339))
	left, err := w.searchAll(ctx, start, mid)
	if err != nil {
		return nil, err
	}
	right, err := w.searchAll(ctx, mid, end)
	if err != nil {
		return nil, err
	}
	return append(left, right...), nil
}

func (w *Worker) processTrace(ctx context.Context, t tempo.SearchTrace, start, end time.Time, stats *windowStats) {
	traces, err := w.tempoService.GetTrace(ctx, t.TraceID, start.Add(-traceLookupPadding), end.Add(traceLookupPadding))
	if err != nil {
		stats.failed.Add(1)
		logrus.Warnf("Failed to fetch trace %s: %v", t.TraceID, err)
		return
	}
	spanCount := countSpans(traces)
	if spanCount == 0 {
		stats.notFound.Add(1)
		logrus.Warnf("Trace %s has no spans", t.TraceID)
		return
	}

	if w.ifService == nil {
		logrus.Infof("[dry run] trace %s root=%s %q spans=%d services=%s",
			t.TraceID, t.RootServiceName, t.RootTraceName, spanCount, strings.Join(serviceNames(traces), ","))
	} else {
		if err := w.ifService.SendTrace(ctx, traces); err != nil {
			stats.failed.Add(1)
			logrus.Warnf("Failed to send trace %s: %v", t.TraceID, err)
			return
		}
		logrus.Debugf("Sent trace %s with %d spans", t.TraceID, spanCount)
	}
	stats.sent.Add(1)
	stats.spans.Add(int64(spanCount))
}
