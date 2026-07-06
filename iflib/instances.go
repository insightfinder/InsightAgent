package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
)

// ListInstances returns the instance names for a project from the systemframework.
// This is the canonical approach — same as used by the MCP server.
func (c *Client) ListInstances(ctx context.Context, projectName string) ([]string, error) {
	return c.ListProjectInstances(ctx, projectName)
}

// InstanceDisplayName maps a display name to the set of real instance names behind it.
type InstanceDisplayName struct {
	DisplayName string
	InstanceSet []string
}

// GetInstanceDisplayNames returns all display-name → instance-name mappings for a project.
// Uses the instanceDisplayNameRequestList parameter format required by the API.
func (c *Client) GetInstanceDisplayNames(ctx context.Context, projectName, customerName string) ([]InstanceDisplayName, error) {
	if customerName == "" {
		customerName = c.userName
	}

	requestList, _ := json.Marshal([]map[string]string{
		{"projectName": projectName, "customerName": customerName},
	})

	params := url.Values{}
	params.Set("instanceDisplayNameRequestList", string(requestList))
	params.Set("tzOffset", "0")

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/instance-display-name", nil, params)
	if err != nil {
		return nil, err
	}
	if status == 404 {
		return nil, nil
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	// Response: [ [projectInfo, [{"instanceDisplayName":"...","instanceSet":[...]},...]], ... ]
	var outer [][]json.RawMessage
	if err := decodeJSON(body, &outer); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	var results []InstanceDisplayName
	for _, entry := range outer {
		if len(entry) < 2 {
			continue
		}
		var items []struct {
			DisplayName string   `json:"instanceDisplayName"`
			InstanceSet []string `json:"instanceSet"`
		}
		if err := decodeJSON(entry[1], &items); err != nil {
			continue
		}
		for _, item := range items {
			if item.DisplayName == "" {
				continue
			}
			results = append(results, InstanceDisplayName{
				DisplayName: item.DisplayName,
				InstanceSet: item.InstanceSet,
			})
		}
	}
	return results, nil
}
