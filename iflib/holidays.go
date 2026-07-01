package iflib

import (
	"context"
	"fmt"
	"net/url"
)

// Holiday represents a named date range during which anomaly detection is suppressed.
type Holiday struct {
	Name      string `json:"name"`
	StartTime int64  `json:"startTime"` // milliseconds
	EndTime   int64  `json:"endTime"`   // milliseconds
}

// GetHolidays returns all holidays configured for a project.
// Uses X-License-Key authentication required by this endpoint.
func (c *Client) GetHolidays(ctx context.Context, projectName string) ([]Holiday, error) {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("customerName", c.userName)

	body, status, err := c.doLicenseKey(ctx, "GET", "/api/external/v1/holiday", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 {
		return []Holiday{}, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var holidays []Holiday
	if err := decodeJSON(body, &holidays); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return holidays, nil
}

// CreateHoliday adds a holiday date range to a project.
// Uses X-License-Key authentication required by this endpoint.
func (c *Client) CreateHoliday(ctx context.Context, projectName string, holiday Holiday) error {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("customerName", c.userName)

	body, status, err := c.doLicenseKey(ctx, "POST", "/api/external/v1/holiday", holiday, params)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}

	var resp struct {
		Success bool   `json:"success"`
		Message string `json:"message,omitempty"`
	}
	if decodeJSON(body, &resp) == nil && !resp.Success {
		return fmt.Errorf("create holiday: %s", resp.Message)
	}
	return nil
}
