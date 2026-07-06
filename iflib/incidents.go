package iflib

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

// TimelineEvent is a single entry returned by the timeline API.
// It may represent an incident, metric anomaly, log anomaly, trace, or deployment.
type TimelineEvent struct {
	Timestamp          int64  `json:"timestamp"`
	PatternName        string `json:"patternName"`
	PatternID          int    `json:"patternId"`
	ComponentName      string `json:"componentName"`
	InstanceName       string `json:"instanceName"`
	ProjectName        string `json:"projectName"`
	ProjectDisplayName string `json:"projectDisplayName"`
	Severity           int    `json:"severity"`
	IsIncident         bool   `json:"isIncident"`
	RootCauseInfoKey   any    `json:"rootCauseInfoKey"`
	IncidentLLMKey     any    `json:"incidentLLMKey"`
}

// TimelineQuery defines the parameters for a timeline request.
type TimelineQuery struct {
	SystemName string
	StartTime  int64    // milliseconds
	EndTime    int64    // milliseconds
	// EventTypes filters the result set. Valid values: "incident", "trace",
	// "loganomaly", "metricanomaly", "deployment". Empty = all types.
	EventTypes []string
}

// GetTimeline retrieves events from the v2 timeline for a system.
func (c *Client) GetTimeline(ctx context.Context, q TimelineQuery) ([]TimelineEvent, error) {
	params := url.Values{}
	params.Set("systemName", q.SystemName)
	params.Set("customerName", c.userName)
	params.Set("startTime", strconv.FormatInt(q.StartTime, 10))
	params.Set("endTime", strconv.FormatInt(q.EndTime, 10))
	if len(q.EventTypes) > 0 {
		params.Set("timelineEventType", strings.Join(q.EventTypes, "|"))
	}

	body, status, err := c.doLicenseKey(ctx, "GET", "/api/v2/timeline", nil, params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var resp struct {
		TimelineList []TimelineEvent `json:"timelineList"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return resp.TimelineList, nil
}

// TimelineDetailQuery defines parameters for the RCA/recommendation detail API.
type TimelineDetailQuery struct {
	// Operation is "RCA" or "Recommendation".
	Operation   string
	QueryString string
	// CustomerName defaults to the client's userName when empty.
	CustomerName string
}

// GetTimelineDetail retrieves RCA or recommendation details for a timeline event.
func (c *Client) GetTimelineDetail(ctx context.Context, q TimelineDetailQuery) (map[string]any, error) {
	customerName := q.CustomerName
	if customerName == "" {
		customerName = c.userName
	}

	params := url.Values{}
	params.Set("operation", q.Operation)
	params.Set("queryString", q.QueryString)
	params.Set("customerName", customerName)

	body, status, err := c.doLicenseKey(ctx, "GET", "/api/v2/timeline-detail", nil, params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var result map[string]any
	if err := decodeJSON(body, &result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result, nil
}

// IncidentSummaryQuery defines parameters for the LLM incident summary API.
type IncidentSummaryQuery struct {
	ProjectName  string
	InstanceName string
	Timestamp    int64
	PatternID    int
	SystemName   string
}

// GetIncidentLLMSummary fetches an AI-generated natural-language summary of an incident.
func (c *Client) GetIncidentLLMSummary(ctx context.Context, q IncidentSummaryQuery) (string, error) {
	params := url.Values{}
	params.Set("userName", c.userName)
	params.Set("projectName", q.ProjectName)
	params.Set("instanceName", q.InstanceName)
	params.Set("timestamp", strconv.FormatInt(q.Timestamp, 10))
	params.Set("patternId", strconv.Itoa(q.PatternID))
	params.Set("systemName", q.SystemName)

	body, status, err := c.doJSON(ctx, "GET", "/api/v1/incident-llm-summary", nil, params)
	if err != nil {
		return "", err
	}
	if status != 200 {
		return "", apiErr(status, body)
	}

	var result struct {
		Summary string `json:"summary"`
		Data    string `json:"data"`
	}
	if decodeJSON(body, &result) == nil && result.Summary != "" {
		return result.Summary, nil
	}
	if result.Data != "" {
		return result.Data, nil
	}
	return string(body), nil
}
