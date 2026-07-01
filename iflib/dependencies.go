package iflib

import (
	"context"
	"encoding/json"
	"fmt"
)

// RelationStatus represents the relationship status between two dependency nodes.
type RelationStatus int

const (
	RelationConfirmed  RelationStatus = 1 // Confirmed
	RelationIgnored    RelationStatus = 2 // Ignored
	RelationInUse      RelationStatus = 3 // In use
	RelationNotInUse   RelationStatus = 4 // Not in use
)

// ParseRelationStatus converts a human-readable string to a RelationStatus.
// Valid values: "Confirmed", "Ignored", "In use", "Not in use".
// Defaults to RelationConfirmed if unrecognised.
func ParseRelationStatus(s string) RelationStatus {
	switch s {
	case "Ignored":
		return RelationIgnored
	case "In use":
		return RelationInUse
	case "Not in use":
		return RelationNotInUse
	default:
		return RelationConfirmed
	}
}

func (r RelationStatus) String() string {
	switch r {
	case RelationIgnored:
		return "Ignored"
	case RelationInUse:
		return "In use"
	case RelationNotInUse:
		return "Not in use"
	default:
		return "Confirmed"
	}
}

// DependencyNode is one endpoint of a dependency relationship.
type DependencyNode struct {
	ID string `json:"id"`
	// Type is "instanceLevel" or "componentLevel".
	Type string `json:"type"`
}

// DependencyRelation is a directed source→target dependency link.
type DependencyRelation struct {
	Sources []DependencyNode `json:"sources"`
	Targets []DependencyNode `json:"targets"`
	// ST is the relationship status: 1=Confirmed, 2=Ignored, 3=In use, 4=Not in use.
	ST RelationStatus `json:"st"`
}

// BuildRelation constructs a simple one-to-one dependency relation.
func BuildRelation(sourceID, targetID, nodeType string, status RelationStatus) DependencyRelation {
	return DependencyRelation{
		Sources: []DependencyNode{{ID: sourceID, Type: nodeType}},
		Targets: []DependencyNode{{ID: targetID, Type: nodeType}},
		ST:      status,
	}
}

type dependencyPayload struct {
	SystemDisplayName             string `json:"systemDisplayName"`
	LicenseKey                    string `json:"licenseKey"`
	UserName                      string `json:"userName"`
	ProjectLevelAddRelationSetStr string `json:"projectLevelAddRelationSetStr"`
	ZoneName                      string `json:"zoneName,omitempty"`
}

// UpdateDependencies sends a set of dependency relations to InsightFinder for a system.
func (c *Client) UpdateDependencies(ctx context.Context, systemDisplayName string, relations []DependencyRelation) error {
	return c.UpdateDependenciesForZone(ctx, systemDisplayName, "", relations)
}

// UpdateDependenciesForZone sends dependency relations scoped to a specific zone within a system.
func (c *Client) UpdateDependenciesForZone(ctx context.Context, systemDisplayName, zoneName string, relations []DependencyRelation) error {
	if len(relations) == 0 {
		return nil
	}

	relationsJSON, err := json.Marshal(relations)
	if err != nil {
		return fmt.Errorf("marshal relations: %w", err)
	}

	payload := dependencyPayload{
		SystemDisplayName:             systemDisplayName,
		LicenseKey:                    c.licenseKey,
		UserName:                      c.userName,
		ProjectLevelAddRelationSetStr: string(relationsJSON),
		ZoneName:                      zoneName,
	}

	body, status, err := c.doJSON(ctx, "POST", "/api/v2/updaterelationdependency", payload, nil)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}
