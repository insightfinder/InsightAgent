package tempo

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"

	config "github.com/insightfinder/grafana-tempo-agent/configs"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

type Service struct {
	config config.TempoConfig
	client *http.Client
}

func NewService(cfg config.TempoConfig) *Service {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	if cfg.InsecureSkipVerify {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}
	return &Service{
		config: cfg,
		client: &http.Client{Timeout: cfg.Timeout.Duration, Transport: transport},
	}
}

func (s *Service) Search(ctx context.Context, start, end time.Time) ([]SearchTrace, error) {
	params := url.Values{}
	params.Set("q", s.config.Query)
	params.Set("start", strconv.FormatInt(start.Unix(), 10))
	params.Set("end", strconv.FormatInt(end.Unix(), 10))
	params.Set("limit", strconv.Itoa(s.config.Limit))
	params.Set("spss", strconv.Itoa(s.config.SpansPerSpanSet))

	body, status, _, err := s.get(ctx, "/api/search", params, "application/json")
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("tempo search returned %d: %s", status, truncate(body, 500))
	}
	var response SearchResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to decode tempo search response: %w", err)
	}
	return response.Traces, nil
}

func (s *Service) GetTrace(ctx context.Context, traceID string, start, end time.Time) (*tracepb.TracesData, error) {
	params := url.Values{}
	if !start.IsZero() && !end.IsZero() {
		params.Set("start", strconv.FormatInt(start.Unix(), 10))
		params.Set("end", strconv.FormatInt(end.Unix(), 10))
	}

	body, status, contentType, err := s.get(ctx, "/api/traces/"+url.PathEscape(traceID), params, "application/protobuf")
	if err != nil {
		return nil, err
	}
	if status == http.StatusNotFound {
		return nil, nil
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("tempo trace %s returned %d: %s", traceID, status, truncate(body, 500))
	}
	traces := &tracepb.TracesData{}
	if err := proto.Unmarshal(body, traces); err != nil {
		return nil, fmt.Errorf("failed to decode trace %s as OTLP protobuf (content-type %q): %w", traceID, contentType, err)
	}
	return traces, nil
}

func (s *Service) get(ctx context.Context, path string, params url.Values, accept string) ([]byte, int, string, error) {
	u := s.config.Endpoint + path
	if len(params) > 0 {
		u += "?" + params.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, 0, "", err
	}
	req.Header.Set("Accept", accept)
	if s.config.Username != "" {
		req.SetBasicAuth(s.config.Username, s.config.Password)
	}
	if s.config.TenantID != "" {
		req.Header.Set("X-Scope-OrgID", s.config.TenantID)
	}
	for k, v := range s.config.Headers {
		req.Header.Set(k, v)
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, 0, "", err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, 0, "", err
	}
	return body, resp.StatusCode, resp.Header.Get("Content-Type"), nil
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "..."
}
