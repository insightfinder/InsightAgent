package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
)

// InstanceMetaFields holds the structured metadata stored per instance in metaDataMap.
type InstanceMetaFields struct {
	LossRatio           string `json:"lossRatio"`
	InstanceType        string `json:"instanceType"`
	InstanceDisplayName string `json:"instanceDisplayName"`
	CoreCount           string `json:"coreCount"`
}

// InstanceGroupingResponse is the raw response from /api/v1/groupingstorag.
// Every map is keyed by instance name (the real name, not the display name).
type InstanceGroupingResponse struct {
	// ComponentName is the component each instance belongs to (appResult in the JSON).
	ComponentName map[string]string `json:"appResult"`

	// IPAddress holds the IP for each instance.
	IPAddress map[string]string `json:"ipAddress"`

	// Zone is the zone name for each instance (zoneData in the JSON).
	Zone map[string]string `json:"zoneData"`

	// SubZone is the sub-zone name for each instance (subZoneData in the JSON).
	SubZone map[string]string `json:"subZoneData"`

	// InstanceGroup is the group each instance belongs to (data in the JSON).
	InstanceGroup map[string]string `json:"data"`

	// ContainerMap lists containers running on each instance.
	ContainerMap map[string][]any `json:"containerMap"`

	// ContainerMetaDataMap lists container metadata for each instance.
	ContainerMetaDataMap map[string][]any `json:"containerMetaDataMap"`

	// InstanceGroupPriority is the alert/grouping priority for each instance.
	InstanceGroupPriority map[string]int `json:"instanceGroupPriority"`

	// HealthPriority is the health-view priority for each instance.
	HealthPriority map[string]int `json:"healthPriority"`

	// MetricInstanceMap maps each instance to its associated metric instance name.
	MetricInstanceMap map[string]string `json:"metricInstanceMap"`

	// IgnoreFlag indicates whether each instance is ignored in anomaly detection.
	IgnoreFlag map[string]bool `json:"ignoreFlagMap"`

	// MetaData contains structured per-instance metadata (loss ratio, display name, etc.).
	MetaData map[string]InstanceMetaFields `json:"metaDataMap"`

	ReachEnd          bool `json:"reachEnd"`
	InstanceListCount int  `json:"instanceListCount"`
}

// InstanceInfo consolidates every piece of metadata for one instance into a flat struct.
type InstanceInfo struct {
	InstanceName          string
	ComponentName         string
	IPAddress             string
	Zone                  string
	SubZone               string
	InstanceGroup         string
	InstanceGroupPriority int
	HealthPriority        int
	MetricInstance        string
	Ignored               bool
	// From metaDataMap:
	LossRatio           string
	InstanceType        string
	DisplayName         string
	CoreCount           string
	// Containers (nil when empty):
	Containers          []any
	ContainerMetaData   []any
}

// ForInstance extracts and consolidates all fields for a single instance name.
func (r *InstanceGroupingResponse) ForInstance(instanceName string) InstanceInfo {
	info := InstanceInfo{
		InstanceName:          instanceName,
		ComponentName:         r.ComponentName[instanceName],
		IPAddress:             r.IPAddress[instanceName],
		Zone:                  r.Zone[instanceName],
		SubZone:               r.SubZone[instanceName],
		InstanceGroup:         r.InstanceGroup[instanceName],
		InstanceGroupPriority: r.InstanceGroupPriority[instanceName],
		HealthPriority:        r.HealthPriority[instanceName],
		MetricInstance:        r.MetricInstanceMap[instanceName],
		Ignored:               r.IgnoreFlag[instanceName],
		Containers:            r.ContainerMap[instanceName],
		ContainerMetaData:     r.ContainerMetaDataMap[instanceName],
	}
	if meta, ok := r.MetaData[instanceName]; ok {
		info.LossRatio = meta.LossRatio
		info.InstanceType = meta.InstanceType
		info.DisplayName = meta.InstanceDisplayName
		info.CoreCount = meta.CoreCount
	}
	return info
}

// AllInstances returns an InstanceInfo for every instance present in the response.
func (r *InstanceGroupingResponse) AllInstances() []InstanceInfo {
	// Use ComponentName as the canonical key set; fall back to IPAddress if needed.
	seen := make(map[string]struct{})
	for k := range r.ComponentName {
		seen[k] = struct{}{}
	}
	for k := range r.IPAddress {
		seen[k] = struct{}{}
	}
	for k := range r.MetaData {
		seen[k] = struct{}{}
	}

	infos := make([]InstanceInfo, 0, len(seen))
	for name := range seen {
		infos = append(infos, r.ForInstance(name))
	}
	return infos
}

// GetInstanceMetadata fetches grouping and metadata for the given instance names
// within a project. Pass the real instance names (not display names).
//
// customerName is the owner of the project; it often equals the client's userName
// but may differ for shared projects.
func (c *Client) GetInstanceMetadata(ctx context.Context, projectName, customerName string, instanceNames []string) (*InstanceGroupingResponse, error) {
	if len(instanceNames) == 0 {
		return nil, fmt.Errorf("instanceNames must not be empty")
	}

	instanceListJSON, err := json.Marshal(instanceNames)
	if err != nil {
		return nil, fmt.Errorf("marshal instance list: %w", err)
	}

	form := url.Values{}
	form.Set("projectName", projectName)
	form.Set("instanceGroup", "All")
	form.Set("instanceList", string(instanceListJSON))
	form.Set("customerName", customerName)

	// /api/external/v1/groupingstorage uses X-API-Key (standard doForm).
	body, status, err := c.doForm(ctx, "POST", "/api/external/v1/groupingstorage", form)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var result InstanceGroupingResponse
	if err := decodeJSON(body, &result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return &result, nil
}
