package main

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

	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

type TempoClient struct {
	cfg  TempoConfig
	http *http.Client
}

type SearchTrace struct {
	TraceID           string `json:"traceID"`
	RootServiceName   string `json:"rootServiceName"`
	RootTraceName     string `json:"rootTraceName"`
	StartTimeUnixNano string `json:"startTimeUnixNano"`
	DurationMs        int64  `json:"durationMs"`
}

type searchResponse struct {
	Traces []SearchTrace `json:"traces"`
}

func NewTempoClient(cfg TempoConfig) *TempoClient {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	if cfg.InsecureSkipVerify {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}
	return &TempoClient{
		cfg:  cfg,
		http: &http.Client{Timeout: cfg.Timeout.Duration, Transport: transport},
	}
}

func (c *TempoClient) newRequest(ctx context.Context, path string, params url.Values, accept string) (*http.Request, error) {
	u := c.cfg.Endpoint + path
	if len(params) > 0 {
		u += "?" + params.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", accept)
	if c.cfg.Username != "" {
		req.SetBasicAuth(c.cfg.Username, c.cfg.Password)
	}
	if c.cfg.TenantID != "" {
		req.Header.Set("X-Scope-OrgID", c.cfg.TenantID)
	}
	for k, v := range c.cfg.Headers {
		req.Header.Set(k, v)
	}
	return req, nil
}

func (c *TempoClient) Search(ctx context.Context, start, end time.Time) ([]SearchTrace, error) {
	params := url.Values{}
	params.Set("q", c.cfg.Query)
	params.Set("start", strconv.FormatInt(start.Unix(), 10))
	params.Set("end", strconv.FormatInt(end.Unix(), 10))
	params.Set("limit", strconv.Itoa(c.cfg.Limit))
	params.Set("spss", strconv.Itoa(c.cfg.SpansPerSpanSet))

	req, err := c.newRequest(ctx, "/api/search", params, "application/json")
	if err != nil {
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("tempo search returned %d: %s", resp.StatusCode, truncate(body, 500))
	}
	var parsed searchResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, fmt.Errorf("decode tempo search response: %w", err)
	}
	return parsed.Traces, nil
}

func (c *TempoClient) GetTrace(ctx context.Context, traceID string, start, end time.Time) (*tracepb.TracesData, error) {
	params := url.Values{}
	if !start.IsZero() && !end.IsZero() {
		params.Set("start", strconv.FormatInt(start.Unix(), 10))
		params.Set("end", strconv.FormatInt(end.Unix(), 10))
	}
	req, err := c.newRequest(ctx, "/api/traces/"+url.PathEscape(traceID), params, "application/protobuf")
	if err != nil {
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("tempo trace %s returned %d: %s", traceID, resp.StatusCode, truncate(body, 500))
	}
	td := &tracepb.TracesData{}
	if err := proto.Unmarshal(body, td); err != nil {
		return nil, fmt.Errorf("decode trace %s as OTLP protobuf (content-type %q): %w", traceID, resp.Header.Get("Content-Type"), err)
	}
	return td, nil
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n]) + "..."
}
