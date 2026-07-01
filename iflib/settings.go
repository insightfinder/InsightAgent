package iflib

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
)

// GetKeywords returns the keyword configuration for a log project.
func (c *Client) GetKeywords(ctx context.Context, projectName string) (map[string]any, error) {
	params := url.Values{}
	params.Set("projectName", projectName)

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/projectkeywords", nil, params)
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

// MetricComponent describes a component that has been escalated or ignored for alerting.
type MetricComponent struct {
	ComponentName string `json:"componentName"`
	MetricName    string `json:"metricName,omitempty"`
}

// GetMetricComponents returns components with the given alert status for a project.
// operation must be "escalateIncident" or "ignored".
func (c *Client) GetMetricComponents(ctx context.Context, projectName, operation string) ([]MetricComponent, error) {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("customerName", c.userName)
	params.Set("operation", operation)
	params.Set("tzOffset", "0")

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/metriccomponent", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 {
		return []MetricComponent{}, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var components []MetricComponent
	if err := decodeJSON(body, &components); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return components, nil
}

// ComponentMetricQuery defines parameters for fetching per-metric alert settings.
type ComponentMetricQuery struct {
	ProjectName     string
	Start           int
	// Limit caps the number of returned settings (0 means no limit / server default of 500000).
	Limit           int
	MetricFilter    string
	OnlyIsKPI       bool
	OnlyComputeDiff bool
}

// ComponentMetricSetting describes per-metric alert configuration returned by the API.
type ComponentMetricSetting struct {
	GlobalSetting map[string]any `json:"globalSetting"`
}

// GetComponentMetricSettings fetches per-metric alert settings for a project.
func (c *Client) GetComponentMetricSettings(ctx context.Context, q ComponentMetricQuery) ([]ComponentMetricSetting, error) {
	limit := q.Limit
	if limit <= 0 {
		limit = 500000
	}

	params := url.Values{}
	params.Set("projectName", fmt.Sprintf("%s@%s", q.ProjectName, c.userName))
	params.Set("customerName", c.userName)
	params.Set("start", strconv.Itoa(q.Start))
	params.Set("limit", strconv.Itoa(limit))
	params.Set("metricFilter", q.MetricFilter)
	params.Set("onlyIsKpi", strconv.FormatBool(q.OnlyIsKPI))
	params.Set("onlyComputeDifference", strconv.FormatBool(q.OnlyComputeDiff))
	params.Set("tzOffset", "0")

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/componentmetricupdate", nil, params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var resp struct {
		MetricSetting []ComponentMetricSetting `json:"metricSetting"`
		ReachEnd      bool                     `json:"reachEnd"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return resp.MetricSetting, nil
}

// GetThirdPartySettings retrieves third-party integration settings (e.g. ServiceNow) for a project.
// cloudType is typically "ServiceNow".
// Uses X-License-Key authentication required by this endpoint.
func (c *Client) GetThirdPartySettings(ctx context.Context, projectName, cloudType string) (map[string]any, error) {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("cloudType", cloudType)
	params.Set("tzOffset", "0")

	body, status, err := c.doLicenseKey(ctx, "GET", "/api/external/v1/thirdpartysetting", nil, params)
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

// GetLogToMetricSettings retrieves log-to-metric conversion rules for a project.
func (c *Client) GetLogToMetricSettings(ctx context.Context, projectName string) ([]map[string]any, error) {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("customerName", c.userName)

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/logtometricsetting", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 {
		return []map[string]any{}, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var result []map[string]any
	if err := decodeJSON(body, &result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result, nil
}
