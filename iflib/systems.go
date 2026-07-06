package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strings"
)

// System represents an InsightFinder system (logical grouping of projects).
type System struct {
	// SystemID is the internal hash identifier used in API calls.
	SystemID        string
	DisplayName     string
	LongTerm        bool
	ShouldAutoShare bool
	// EnableCompositeTimeline controls composite-timeline behaviour for the system.
	EnableCompositeTimeline bool
	Projects                []ProjectInfo
}

// ProjectInfo is a lightweight project descriptor returned when listing projects within a system.
type ProjectInfo struct {
	ProjectName        string `json:"projectName"`
	ProjectDisplayName string `json:"projectDisplayName,omitempty"`
	UserName           string `json:"userName,omitempty"`
	DataType           string `json:"dataType,omitempty"`
	InsightAgentType   string `json:"insightAgentType,omitempty"`
	InstanceType       string `json:"instanceType,omitempty"`
	ProjectCloudType   string `json:"projectCloudType,omitempty"`
	// InstanceList contains the instance names registered for this project (from systemframework).
	InstanceList []any `json:"instanceList,omitempty"`
}

type rawSystemEntry struct {
	SystemKey struct {
		SystemName string `json:"systemName"`
	} `json:"systemKey"`
	SystemName         string `json:"systemName,omitempty"`
	SystemDisplayName  string `json:"systemDisplayName"`
	LongTerm           bool   `json:"longTerm"`
	SystemSetting      string `json:"systemSetting,omitempty"`      // embedded JSON string
	ProjectDetailsList string `json:"projectDetailsList,omitempty"` // embedded JSON string
}

type systemFrameworkResponse struct {
	OwnSystemArr   []json.RawMessage `json:"ownSystemArr"`
	ShareSystemArr []json.RawMessage `json:"shareSystemArr"`
}

// parseRawEntry handles entries that may arrive as a JSON object or as a
// JSON-encoded string containing a JSON object (both seen in production).
func parseRawEntry(raw json.RawMessage) (*rawSystemEntry, error) {
	var entry rawSystemEntry
	if err := json.Unmarshal(raw, &entry); err == nil {
		return &entry, nil
	}
	// Try unwrapping a quoted string.
	var s string
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil, fmt.Errorf("parse system entry: %w", err)
	}
	if err := json.Unmarshal([]byte(s), &entry); err != nil {
		return nil, fmt.Errorf("parse system entry (inner): %w", err)
	}
	return &entry, nil
}

func rawEntryToSystem(e *rawSystemEntry) System {
	id := e.SystemKey.SystemName
	if id == "" {
		id = e.SystemName
	}

	sys := System{
		SystemID:    id,
		DisplayName: e.SystemDisplayName,
		LongTerm:    e.LongTerm,
	}

	if e.SystemSetting != "" {
		var setting map[string]any
		if json.Unmarshal([]byte(e.SystemSetting), &setting) == nil {
			if v, ok := setting["shouldAutoShare"].(bool); ok {
				sys.ShouldAutoShare = v
			}
			if v, ok := setting["enableCompositeTimeline"].(bool); ok {
				sys.EnableCompositeTimeline = v
			}
		}
	}

	if e.ProjectDetailsList != "" {
		var projects []ProjectInfo
		if json.Unmarshal([]byte(e.ProjectDetailsList), &projects) == nil {
			sys.Projects = projects
		}
	}

	return sys
}

// ListSystems returns all systems (owned + shared) visible to the authenticated user.
func (c *Client) ListSystems(ctx context.Context) ([]System, error) {
	params := url.Values{}
	params.Set("customerName", c.userName)
	params.Set("needDetail", "true")
	params.Set("tzOffset", "0")

	body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/systemframework", nil, params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var fw systemFrameworkResponse
	if err := decodeJSON(body, &fw); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	all := append(fw.OwnSystemArr, fw.ShareSystemArr...)
	systems := make([]System, 0, len(all))
	for _, raw := range all {
		entry, err := parseRawEntry(raw)
		if err != nil {
			continue
		}
		systems = append(systems, rawEntryToSystem(entry))
	}
	return systems, nil
}

// ResolveSystemID maps a human-readable system display name to its internal system ID.
// Matching is case-insensitive; falls back to matching on SystemID directly.
func (c *Client) ResolveSystemID(ctx context.Context, displayName string) (string, error) {
	systems, err := c.ListSystems(ctx)
	if err != nil {
		return "", err
	}

	needle := strings.ToLower(strings.TrimSpace(displayName))
	for _, sys := range systems {
		if strings.ToLower(sys.DisplayName) == needle || strings.ToLower(sys.SystemID) == needle {
			return sys.SystemID, nil
		}
	}
	return "", fmt.Errorf("system %q not found", displayName)
}

// ListProjectInstances returns the instance names for a project by searching the systemframework.
// This is the canonical way to list instances — the same approach used by the MCP server.
// projectName may be the project name or display name (case-insensitive).
func (c *Client) ListProjectInstances(ctx context.Context, projectName string) ([]string, error) {
	systems, err := c.ListSystems(ctx)
	if err != nil {
		return nil, err
	}

	needle := strings.ToLower(strings.TrimSpace(projectName))
	for _, sys := range systems {
		for _, proj := range sys.Projects {
			if strings.ToLower(proj.ProjectName) == needle || strings.ToLower(proj.ProjectDisplayName) == needle {
				names := make([]string, 0, len(proj.InstanceList))
				for _, inst := range proj.InstanceList {
					if inst != nil {
						names = append(names, fmt.Sprintf("%v", inst))
					}
				}
				return names, nil
			}
		}
	}
	return nil, fmt.Errorf("project %q not found in system framework", projectName)
}

// ListProjects returns all projects inside the named system.
// systemName may be the display name or the internal system ID.
func (c *Client) ListProjects(ctx context.Context, systemName string) ([]ProjectInfo, error) {
	systems, err := c.ListSystems(ctx)
	if err != nil {
		return nil, err
	}

	needle := strings.ToLower(strings.TrimSpace(systemName))
	for _, sys := range systems {
		if strings.ToLower(sys.DisplayName) == needle || strings.ToLower(sys.SystemID) == needle {
			return sys.Projects, nil
		}
	}
	return nil, fmt.Errorf("system %q not found", systemName)
}

// SystemSettings aggregates all system-level configuration for a given system ID.
type SystemSettings struct {
	SystemID                string
	LongTerm                bool
	ShouldAutoShare         bool
	EnableCompositeTimeline bool
	KnowledgeBase           map[string]any // from /api/external/v1/globalknowledgebasesetting
	IncidentPrediction      map[string]any // from /api/external/v2/IncidentPredictionSetting
	HealthView              map[string]any // from /api/external/v2/healthviewsetting
}

// GetSystemSettings fetches all system-level configuration for the given system ID.
// Individual sub-request failures are silently skipped so partial data is still returned.
func (c *Client) GetSystemSettings(ctx context.Context, systemID string) (*SystemSettings, error) {
	settings := &SystemSettings{SystemID: systemID}

	systemIDsJSON, _ := json.Marshal([]string{systemID})
	systemIDsStr := string(systemIDsJSON)

	// Global knowledge base settings
	{
		params := url.Values{}
		params.Set("customerName", c.userName)
		params.Set("systemIds", systemIDsStr)
		if body, status, err := c.doJSON(ctx, "GET", "/api/external/v1/globalknowledgebasesetting", nil, params); err == nil && status == 200 {
			var data []map[string]any
			if decodeJSON(body, &data) == nil && len(data) > 0 {
				settings.KnowledgeBase = data[0]
			}
		}
	}

	// Incident prediction settings
	{
		params := url.Values{}
		params.Set("customerName", c.userName)
		params.Set("systemIds", systemIDsStr)
		if body, status, err := c.doJSON(ctx, "GET", "/api/external/v2/IncidentPredictionSetting", nil, params); err == nil && status == 200 {
			var data []map[string]any
			if decodeJSON(body, &data) == nil && len(data) > 0 {
				settings.IncidentPrediction = data[0]
			}
		}
	}

	// Health view / notifications settings — response is a map keyed by system ID.
	{
		params := url.Values{}
		params.Set("customerName", c.userName)
		if body, status, err := c.doJSON(ctx, "GET", "/api/external/v2/healthviewsetting", nil, params); err == nil && status == 200 {
			var data map[string]map[string]any
			if decodeJSON(body, &data) == nil {
				settings.HealthView = data[systemID]
			}
		}
	}

	// Miscellaneous flags from system framework.
	if systems, err := c.ListSystems(ctx); err == nil {
		for _, sys := range systems {
			if sys.SystemID == systemID {
				settings.LongTerm = sys.LongTerm
				settings.ShouldAutoShare = sys.ShouldAutoShare
				settings.EnableCompositeTimeline = sys.EnableCompositeTimeline
				break
			}
		}
	}

	return settings, nil
}
