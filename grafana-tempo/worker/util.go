package worker

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

func countSpans(traces *tracepb.TracesData) int {
	if traces == nil {
		return 0
	}
	count := 0
	for _, rs := range traces.ResourceSpans {
		for _, ss := range rs.ScopeSpans {
			count += len(ss.Spans)
		}
	}
	return count
}

func serviceNames(traces *tracepb.TracesData) []string {
	seen := map[string]struct{}{}
	names := []string{}
	for _, rs := range traces.ResourceSpans {
		for _, kv := range rs.GetResource().GetAttributes() {
			if kv.Key != "service.name" {
				continue
			}
			name := kv.GetValue().GetStringValue()
			if _, ok := seen[name]; !ok {
				seen[name] = struct{}{}
				names = append(names, name)
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
		logrus.Warnf("Ignoring invalid state file %s: %v", path, err)
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
		return fmt.Errorf("failed to rename state file: %w", err)
	}
	return nil
}
