package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strings"
)

// CausalGroup represents an InsightFinder causal dependency group.
type CausalGroup struct {
	CausalKey   string
	CausalName  string
	Owner       string
	ProjectList []CausalProject
}

// CausalProject is a project entry within a causal group.
type CausalProject struct {
	ProjectName  string `json:"projectName"`
	CustomerName string `json:"customerName"`
	ProjectType  string `json:"projectType"`
	Grouping     string `json:"grouping"`
	Type         string `json:"type"`
}

// GetCausalGroups returns all causal groups visible to the authenticated user.
// Requires session authentication (password must be set).
func (c *Client) GetCausalGroups(ctx context.Context) ([]CausalGroup, error) {
	params := url.Values{}
	params.Set("customerName", c.userName)

	body, status, err := c.doSessionGet(ctx, "/api/v1/causalgroup", params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var outer struct {
		Data string `json:"data"`
	}
	if err := decodeJSON(body, &outer); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	var raw map[string]json.RawMessage
	if err := decodeJSON([]byte(outer.Data), &raw); err != nil {
		return nil, fmt.Errorf("decode causal group data: %w", err)
	}

	groups := make([]CausalGroup, 0, len(raw))
	for key, val := range raw {
		var g struct {
			CausalName  string `json:"causalName"`
			Owner       string `json:"owner"`
			ProjectList string `json:"projectList"` // JSON string
		}
		if err := decodeJSON(val, &g); err != nil {
			continue
		}

		cg := CausalGroup{
			CausalKey:  key,
			CausalName: g.CausalName,
			Owner:      g.Owner,
		}

		var projects []CausalProject
		if g.ProjectList != "" {
			decodeJSON([]byte(g.ProjectList), &projects) //nolint:errcheck
		}
		cg.ProjectList = projects
		groups = append(groups, cg)
	}
	return groups, nil
}

// FindCausalGroupByName returns the first causal group whose name contains the given
// string (case-insensitive). Returns nil if not found.
func (c *Client) FindCausalGroupByName(ctx context.Context, name string) (*CausalGroup, error) {
	groups, err := c.GetCausalGroups(ctx)
	if err != nil {
		return nil, err
	}
	needle := strings.ToLower(strings.TrimSpace(name))
	for i := range groups {
		if strings.Contains(strings.ToLower(groups[i].CausalName), needle) {
			return &groups[i], nil
		}
	}
	return nil, nil
}

// DependencyZoneMeta describes relation counts for one zone inside a causal group.
type DependencyZoneMeta struct {
	Zone            string
	HaveRelationSize int
	NoRelationSize   int
}

// DependencyRelationMeta holds metadata about a causal group's dependency relations.
type DependencyRelationMeta struct {
	Zones           []DependencyZoneMeta
	AllPossibleZones []string
}

// GetDependencyRelationMetadata returns relation metadata for a causal group.
// Requires session authentication.
func (c *Client) GetDependencyRelationMetadata(ctx context.Context, causalKey string) (*DependencyRelationMeta, error) {
	params := url.Values{}
	params.Set("customerName", c.userName)
	params.Set("causalKey", causalKey)

	body, status, err := c.doSessionGet(ctx, "/api/v2/dependencyrelation-metadata", params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var raw struct {
		DependencyMetadata string `json:"dependencyMetadata"` // JSON string
		AllPossibleZone    string `json:"allPossibleZone"`    // JSON string
	}
	if err := decodeJSON(body, &raw); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	result := &DependencyRelationMeta{}

	var zones []struct {
		Zone     string `json:"zone"`
		Metadata struct {
			HaveRelationSize int `json:"haveRelationSize"`
			NoRelationSize   int `json:"noRelationSize"`
		} `json:"metadata"`
	}
	if raw.DependencyMetadata != "" {
		decodeJSON([]byte(raw.DependencyMetadata), &zones) //nolint:errcheck
	}
	for _, z := range zones {
		result.Zones = append(result.Zones, DependencyZoneMeta{
			Zone:             z.Zone,
			HaveRelationSize: z.Metadata.HaveRelationSize,
			NoRelationSize:   z.Metadata.NoRelationSize,
		})
	}

	if raw.AllPossibleZone != "" {
		decodeJSON([]byte(raw.AllPossibleZone), &result.AllPossibleZones) //nolint:errcheck
	}

	return result, nil
}

// rawRelation is the abbreviated format the GET endpoint returns.
type rawRelation struct {
	Source struct {
		ID   string `json:"id"`
		Type string `json:"type"` // "i" = instanceLevel, "c" = componentLevel
	} `json:"s"`
	Target struct {
		ID   string `json:"id"`
		Type string `json:"type"`
	} `json:"t"`
	ST RelationStatus `json:"st"`
}

func expandType(abbr string) string {
	switch abbr {
	case "i":
		return "instanceLevel"
	case "c":
		return "componentLevel"
	default:
		return abbr
	}
}

func relationKey(sourceID, targetID string) string {
	return sourceID + "→" + targetID
}

// GetDependencyRelations fetches the existing dependency relations for a causal group zone.
// Returns them in the write format (sources/targets) ready to be POSTed back after merging.
// Requires session authentication.
func (c *Client) GetDependencyRelations(ctx context.Context, causalKey, zoneName string) ([]DependencyRelation, error) {
	params := url.Values{}
	params.Set("customerName", c.userName)
	params.Set("causalKey", causalKey)
	if zoneName != "" {
		params.Set("causalZoneName", zoneName)
	}

	body, status, err := c.doSessionGet(ctx, "/api/v2/dependencyrelation", params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var resp struct {
		DependencyMap []struct {
			DependencyData []rawRelation `json:"dependencyData"`
		} `json:"dependencyMap"`
	}
	if err := decodeJSON(body, &resp); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	var relations []DependencyRelation
	for _, entry := range resp.DependencyMap {
		for _, r := range entry.DependencyData {
			relations = append(relations, DependencyRelation{
				Sources: []DependencyNode{{ID: r.Source.ID, Type: expandType(r.Source.Type)}},
				Targets: []DependencyNode{{ID: r.Target.ID, Type: expandType(r.Target.Type)}},
				ST:      r.ST,
			})
		}
	}
	return relations, nil
}

// UpsertDependencyRelations fetches existing relations, applies the updates (matched by
// source+target ID), preserves all others, and POSTs the complete merged list back.
// This avoids overwriting relations that are not included in the update set.
// Requires session authentication.
func (c *Client) UpsertDependencyRelations(ctx context.Context, causalKey, zoneName string, updates []DependencyRelation) error {
	existing, err := c.GetDependencyRelations(ctx, causalKey, zoneName)
	if err != nil {
		return fmt.Errorf("fetch existing relations: %w", err)
	}

	// Build lookup from update list: sourceID→targetID → updated relation.
	updateMap := make(map[string]DependencyRelation, len(updates))
	for _, u := range updates {
		if len(u.Sources) > 0 && len(u.Targets) > 0 {
			updateMap[relationKey(u.Sources[0].ID, u.Targets[0].ID)] = u
		}
	}

	// Merge: apply updates over existing, keep untouched ones as-is.
	merged := make([]DependencyRelation, 0, len(existing)+len(updates))
	seen := make(map[string]struct{}, len(existing))
	for _, r := range existing {
		if len(r.Sources) == 0 || len(r.Targets) == 0 {
			continue
		}
		key := relationKey(r.Sources[0].ID, r.Targets[0].ID)
		seen[key] = struct{}{}
		if updated, ok := updateMap[key]; ok {
			merged = append(merged, updated) // apply new status
		} else {
			merged = append(merged, r) // keep unchanged
		}
	}
	// Add brand-new relations not previously in the list.
	for _, u := range updates {
		if len(u.Sources) == 0 || len(u.Targets) == 0 {
			continue
		}
		key := relationKey(u.Sources[0].ID, u.Targets[0].ID)
		if _, exists := seen[key]; !exists {
			merged = append(merged, u)
		}
	}

	return c.UpdateDependencyRelations(ctx, causalKey, zoneName, merged)
}

// UpdateDependencyRelations replaces ALL dependency relations for a causal group zone
// with the provided list. Use UpsertDependencyRelations to preserve existing relations.
// Requires session authentication.
func (c *Client) UpdateDependencyRelations(ctx context.Context, causalKey, zoneName string, relations []DependencyRelation) error {
	if len(relations) == 0 {
		return nil
	}

	payload, err := json.Marshal(relations)
	if err != nil {
		return fmt.Errorf("marshal relations: %w", err)
	}

	params := url.Values{}
	params.Set("customerName", c.userName)
	params.Set("causalKey", causalKey)
	if zoneName != "" {
		params.Set("causalZoneName", zoneName)
	}

	body, status, err := c.doSessionMultipart(ctx, "/api/v2/dependencyrelation", params, payload)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}

	var resp struct {
		Success bool   `json:"success"`
		Message string `json:"message"`
	}
	if decodeJSON(body, &resp) == nil && !resp.Success {
		return fmt.Errorf("update dependency relations: %s", resp.Message)
	}
	return nil
}
