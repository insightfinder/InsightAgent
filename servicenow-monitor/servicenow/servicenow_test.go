package servicenow

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	config "github.com/insightfinder/servicenow-monitor/configs"
)

// newTestClient points a client at a fake ServiceNow whose create and read
// endpoints each fail the first `failures` calls with a 503.
func newTestClient(t *testing.T, failures, maxRetries int) (*Client, *int, *int) {
	creates, reads := 0, 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == INCIDENT_API:
			creates++
			if creates <= failures {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			w.WriteHeader(http.StatusCreated)
		case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, INCIDENT_API+"/abc"):
			reads++
			if reads <= failures {
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
		default:
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Write([]byte(`{"result":{"sys_id":"abc","number":"INC0000001"}}`))
	}))
	t.Cleanup(srv.Close)

	inst := config.ServiceNowInstance{Name: "test", URL: srv.URL, Username: "u", Password: "p", Enabled: true}
	cfg := config.ServiceNowConfig{TimeoutSec: 5, MaxRetries: maxRetries}
	return NewClient(inst, cfg), &creates, &reads
}

func TestHealthCheckRecoversWithinRetries(t *testing.T) {
	c, creates, reads := newTestClient(t, 3, 10)
	if err := c.HealthCheck(); err != nil {
		t.Fatalf("expected success after retries, got %v", err)
	}
	if *creates != 4 || *reads != 4 {
		t.Fatalf("expected 4 creates and 4 reads, got %d and %d", *creates, *reads)
	}
}

func TestHealthCheckFailsAfterMaxRetries(t *testing.T) {
	c, creates, _ := newTestClient(t, 100, 10)
	if err := c.HealthCheck(); err == nil {
		t.Fatal("expected failure")
	}
	if *creates != 10 {
		t.Fatalf("expected 10 create attempts, got %d", *creates)
	}
}
