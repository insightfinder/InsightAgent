// venue-ids — set Jira venue/subvenue/location/device IDs on InsightFinder instances.
//
// Once per run, it bulk-fetches every device, dependency edge, and venue
// abbreviation from the AccessParks asset server (GET /devices/export,
// /devices/edges/export, /venues/abbreviations) and builds in-memory indexes —
// one HTTP round trip per dataset instead of one per instance, since a run
// processes thousands of instances across all configured projects.
//
// For each configured project it then:
//  1. Lists all instances from InsightFinder.
//  2. Strips the "MAC ", "SERIAL ", or "JIRAKEY " prefix from each instance name to
//     obtain the raw identifier (e.g. "4C:B1:CD:38:3C:60", "IHS-23344", "ABC123SS").
//     Instances with none of these prefixes (e.g. "host.13884") fall back to: the
//     instance's IP address, then the instance name as-is, then the instance name
//     with "." replaced by "_".
//  3. Resolves the identifier against the local device index (mirrors the asset
//     server's GET /devices/{identifier} matching).
//  4. Reads venue_id, subvenue_id, location_id, device_id from the device meta.
//     If no device matches by any of the above, falls back to the venue
//     abbreviation prefix of the instance name (e.g. "HE-RAD_C5-Helena62" →
//     "he") via the local venue-abbreviation index, populating whatever
//     venue-level fields are available.
//  5. Uploads the Jira custom-field values to InsightFinder via
//     /api/v1/agent-upload-third-party-instancemetadata.
//
// Usage:
//
//	go run main.go [-config config.yaml] [-dry-run]
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/insightfinder/InsightAgent/iflib"
	"gopkg.in/yaml.v3"
)

// ── Config ────────────────────────────────────────────────────────────────────

type Config struct {
	InsightFinder IFConfig    `yaml:"insightfinder"`
	AssetServer   AssetConfig `yaml:"asset_server"`
	Jira          JiraConfig  `yaml:"jira"`
	Projects      []string    `yaml:"projects"`
	// MetadataBatchSize controls how many instance names are sent per
	// InsightFinder groupingstorage request when resolving IP addresses for
	// instances with no MAC/SERIAL/JIRAKEY prefix. Defaults to 100.
	MetadataBatchSize int `yaml:"metadata_batch_size"`
}

type IFConfig struct {
	URL        string `yaml:"url"`
	Username   string `yaml:"username"`
	LicenseKey string `yaml:"license_key"`
	Password   string `yaml:"password"`
}

type AssetConfig struct {
	URL    string `yaml:"url"`
	APIKey string `yaml:"api_key"`
	// UpstreamMaxDepth is the max_depth param sent to GET /devices/{id}/upstream.
	// Defaults to 1 (immediate upstream device only).
	UpstreamMaxDepth int `yaml:"upstream_max_depth"`
}

// JiraConfig holds Jira workspace settings and the mapping from device meta keys
// to Jira custom field IDs.
//
// FieldMapping example:
//
//	venue_id:    customfield_10060
//	subvenue_id: customfield_10078
//	location_id: customfield_10062
//	device_id:   customfield_10076
type JiraConfig struct {
	WorkspaceID  string            `yaml:"workspace_id"`
	FieldMapping map[string]string `yaml:"field_mapping"`
}

func loadConfig(path string) (*Config, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	defer f.Close()

	var cfg Config
	if err := yaml.NewDecoder(f).Decode(&cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}
	return &cfg, nil
}

func validateConfig(cfg *Config) error {
	if cfg.InsightFinder.URL == "" {
		return fmt.Errorf("insightfinder.url is required")
	}
	if cfg.InsightFinder.Username == "" {
		return fmt.Errorf("insightfinder.username is required")
	}
	if cfg.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder.license_key is required")
	}
	if cfg.AssetServer.URL == "" {
		return fmt.Errorf("asset_server.url is required")
	}
	if cfg.AssetServer.APIKey == "" {
		return fmt.Errorf("asset_server.api_key is required")
	}
	if cfg.Jira.WorkspaceID == "" {
		return fmt.Errorf("jira.workspace_id is required")
	}
	if len(cfg.Jira.FieldMapping) == 0 {
		return fmt.Errorf("jira.field_mapping must have at least one entry")
	}
	if len(cfg.Projects) == 0 {
		return fmt.Errorf("projects list is empty")
	}
	if cfg.AssetServer.UpstreamMaxDepth <= 0 {
		cfg.AssetServer.UpstreamMaxDepth = 1
	}
	if cfg.MetadataBatchSize <= 0 {
		cfg.MetadataBatchSize = 500
	}
	return nil
}

// ── Asset server client ───────────────────────────────────────────────────────

type assetClient struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

func newAssetClient(baseURL, apiKey string) *assetClient {
	return &assetClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		apiKey:  apiKey,
		// This client now makes exactly 3 bulk-export requests per run rather
		// than one per instance, so a generous timeout is fine — 32k+ device
		// rows with model joins can take a while to query and serialize.
		httpClient: &http.Client{Timeout: 120 * time.Second},
	}
}

// DeviceResponse mirrors one entry of the GET /devices/export response (same
// shape as GET /devices/{id}).
type DeviceResponse struct {
	ID           string                 `json:"id"`
	ObjectKey    string                 `json:"object_key"`
	Name         string                 `json:"name"`
	DeviceName   string                 `json:"device_name"`
	IPAddress    string                 `json:"ip_address"`
	MacAddress   string                 `json:"mac_address"`
	SerialNumber string                 `json:"serial_number"`
	Meta         map[string]interface{} `json:"meta"`

	// Pre-resolved Jira object keys (e.g. "IHS-20846"). May be null/empty when
	// the corresponding Jira object hasn't been created yet.
	JiraDeviceKey   string `json:"jira_device_key"`
	JiraLocationKey string `json:"jira_location_key"`
	JiraSubvenueKey string `json:"jira_subvenue_key"`
	JiraVenueKey    string `json:"jira_venue_key"`
	JiraModelKey    string `json:"jira_model_key"`

	// Human-readable names for the objects above. May be empty when the
	// corresponding Jira object hasn't been created yet.
	JiraDeviceName     string `json:"jira_device_name"`
	JiraLocationName   string `json:"jira_location_name"`
	JiraSubvenueName   string `json:"jira_subvenue_name"`
	JiraVenueName      string `json:"jira_venue_name"`
	JiraModelName      string `json:"jira_model_name"`
	JiraModelclassName string `json:"jira_modelclass_name"`
}

// VenueResponse mirrors one entry of the GET /venues/abbreviations response.
type VenueResponse struct {
	Abbreviation string `json:"abbreviation"`
	VenueName    string `json:"venue_name"`
	VenueKey     string `json:"venue_key"`
	VenueID      string `json:"venue_id"`
}

// EdgeResponse mirrors one entry of the GET /devices/edges/export response.
// source_id → target_id means source is upstream of target.
type EdgeResponse struct {
	SourceID         string `json:"source_id"`
	TargetID         string `json:"target_id"`
	RelationshipType string `json:"relationship_type"`
}

// UpstreamDevice is the nearest-first upstream chain of a device, computed
// locally by edgeIndex.upstream() (mirrors the asset server's
// GET /devices/{id}/upstream response shape).
type UpstreamDevice struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	ObjectKey  string `json:"object_key"`
	MacAddress string `json:"mac_address"`
	Depth      int    `json:"depth"`
}

// bulkGet issues an authenticated GET against the asset server and decodes
// the JSON response body into out.
func (a *assetClient) bulkGet(ctx context.Context, path string, out interface{}) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, a.baseURL+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("X-API-Key", a.apiKey)
	req.Header.Set("Accept", "application/json")
	// Deliberately not setting Accept-Encoding: net/http only auto-decompresses
	// gzip responses when it adds that header itself — an explicit value here
	// would disable transparent decompression and leave the raw gzip bytes.

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("decode: %w", err)
	}
	return nil
}

// exportDevices fetches every device in one call via GET /devices/export.
func (a *assetClient) exportDevices(ctx context.Context) ([]DeviceResponse, error) {
	var devices []DeviceResponse
	if err := a.bulkGet(ctx, "/devices/export", &devices); err != nil {
		return nil, err
	}
	return devices, nil
}

// exportEdges fetches every dependency edge in one call via
// GET /devices/edges/export.
func (a *assetClient) exportEdges(ctx context.Context) ([]EdgeResponse, error) {
	var edges []EdgeResponse
	if err := a.bulkGet(ctx, "/devices/edges/export", &edges); err != nil {
		return nil, err
	}
	return edges, nil
}

// exportVenueAbbreviations fetches every abbreviation → venue mapping in one
// call via GET /venues/abbreviations.
func (a *assetClient) exportVenueAbbreviations(ctx context.Context) ([]VenueResponse, error) {
	var venues []VenueResponse
	if err := a.bulkGet(ctx, "/venues/abbreviations", &venues); err != nil {
		return nil, err
	}
	return venues, nil
}

// ── In-memory indexes ─────────────────────────────────────────────────────────
// Built once per run from the bulk exports above, so per-instance resolution
// is a map lookup instead of an HTTP request.

// deviceIndex is a case-insensitive multi-key index over every device,
// mirroring DeviceRepository.find_device()'s OR-matching semantics
// (id, object_key, name, device_name, ip_address, mac_address, serial_number).
type deviceIndex struct {
	byID  map[string]*DeviceResponse
	byKey map[string]*DeviceResponse
}

func newDeviceIndex(devices []DeviceResponse) *deviceIndex {
	idx := &deviceIndex{
		byID:  make(map[string]*DeviceResponse, len(devices)),
		byKey: make(map[string]*DeviceResponse, len(devices)*4),
	}
	for i := range devices {
		d := &devices[i]
		idx.byID[d.ID] = d
		for _, key := range []string{d.ID, d.ObjectKey, d.Name, d.DeviceName, d.IPAddress, d.MacAddress, d.SerialNumber} {
			if key == "" {
				continue
			}
			lk := strings.ToLower(key)
			if _, exists := idx.byKey[lk]; !exists {
				idx.byKey[lk] = d
			}
		}
	}
	return idx
}

// find looks up a device by any identifier (case-insensitive), or nil if none match.
func (idx *deviceIndex) find(identifier string) *DeviceResponse {
	return idx.byKey[strings.ToLower(identifier)]
}

// edgeIndex is an adjacency index over every dependency edge, for computing a
// device's upstream chain locally instead of via GET /devices/{id}/upstream.
type edgeIndex struct {
	upstreamOf map[string][]string // target_id → []source_id
}

func newEdgeIndex(edges []EdgeResponse) *edgeIndex {
	idx := &edgeIndex{upstreamOf: make(map[string][]string, len(edges))}
	for _, e := range edges {
		idx.upstreamOf[e.TargetID] = append(idx.upstreamOf[e.TargetID], e.SourceID)
	}
	return idx
}

// upstream returns deviceID's upstream chain (nearest first) up to maxDepth
// hops, mirroring DeviceRepository.get_upstream()'s "ORDER BY MIN(depth)".
func (idx *edgeIndex) upstream(deviceID string, maxDepth int, devices *deviceIndex) []UpstreamDevice {
	depthOf := map[string]int{}
	seen := map[string]bool{deviceID: true}
	frontier := []string{deviceID}

	for depth := 1; depth <= maxDepth && len(frontier) > 0; depth++ {
		var next []string
		for _, id := range frontier {
			for _, srcID := range idx.upstreamOf[id] {
				if seen[srcID] {
					continue
				}
				seen[srcID] = true
				depthOf[srcID] = depth
				next = append(next, srcID)
			}
		}
		frontier = next
	}
	if len(depthOf) == 0 {
		return nil
	}

	ids := make([]string, 0, len(depthOf))
	for id := range depthOf {
		ids = append(ids, id)
	}
	sort.SliceStable(ids, func(i, j int) bool { return depthOf[ids[i]] < depthOf[ids[j]] })

	out := make([]UpstreamDevice, 0, len(ids))
	for _, id := range ids {
		d := devices.byID[id]
		if d == nil {
			continue
		}
		out = append(out, UpstreamDevice{
			ID: d.ID, Name: d.Name, ObjectKey: d.ObjectKey, MacAddress: d.MacAddress, Depth: depthOf[id],
		})
	}
	return out
}

// venueIndex is a case-insensitive index over every abbreviation → venue mapping.
type venueIndex map[string]*VenueResponse

func newVenueIndex(venues []VenueResponse) venueIndex {
	idx := make(venueIndex, len(venues))
	for i := range venues {
		idx[strings.ToLower(venues[i].Abbreviation)] = &venues[i]
	}
	return idx
}

func (idx venueIndex) find(abbreviation string) *VenueResponse {
	return idx[strings.ToLower(abbreviation)]
}

// ── Instance name parsing ─────────────────────────────────────────────────────

// parseIdentifier strips the InsightFinder identifier prefix from an instance name
// and returns the raw value to use for an asset server lookup.
//
// Recognized prefixes (set by getmessages_zabbix.py):
//
//	"MAC "     → MAC address, e.g. "4C:B1:CD:38:3C:60"
//	"SERIAL "  → serial number, e.g. "ABC123SS"
//	"JIRAKEY " → Jira object key, e.g. "IHS-23344"
//
// Returns ("", false) when no prefix is found.
func parseIdentifier(instanceName string) (identifier string, ok bool) {
	switch {
	case strings.HasPrefix(instanceName, "MAC "):
		// Zabbix agent stores MACs with dashes (e.g. "18-4B-0D-13-C3-70");
		// the asset server expects colons ("18:4B:0D:13:C3:70").
		mac := strings.TrimPrefix(instanceName, "MAC ")
		return strings.ReplaceAll(mac, "-", ":"), true
	case strings.HasPrefix(instanceName, "SERIAL "):
		return strings.TrimPrefix(instanceName, "SERIAL "), true
	case strings.HasPrefix(instanceName, "JIRAKEY "):
		return strings.TrimPrefix(instanceName, "JIRAKEY "), true
	}
	return "", false
}

// fetchInstanceIPs looks up the IP address of each instance name via InsightFinder's
// groupingstorage metadata, in batches. Used as the first fallback for instances
// with no recognized MAC/SERIAL/JIRAKEY prefix (e.g. "host.13884").
func fetchInstanceIPs(ctx context.Context, ifClient *iflib.Client, project, customerName string, names []string, batchSize int) (map[string]string, error) {
	if len(names) == 0 {
		return nil, nil
	}

	ips := make(map[string]string, len(names))
	for i := 0; i < len(names); i += batchSize {
		end := i + batchSize
		if end > len(names) {
			end = len(names)
		}
		batch := names[i:end]

		meta, err := ifClient.GetInstanceMetadata(ctx, project, customerName, batch)
		if err != nil {
			return nil, fmt.Errorf("metadata batch %d: %w", i/batchSize, err)
		}
		for _, name := range batch {
			ips[name] = meta.ForInstance(name).IPAddress
		}
	}
	return ips, nil
}

// identifierCandidates returns the ordered list of asset-server lookup identifiers
// to try for an instance with no recognized prefix:
//  1. its IP address (if known)
//  2. the instance name as-is (e.g. "host.13884")
//  3. the instance name with "." replaced by "_" (e.g. "host_13884")
func identifierCandidates(instanceName, ip string) []string {
	var candidates []string
	if ip != "" {
		candidates = append(candidates, ip)
	}
	candidates = append(candidates, instanceName)
	if underscored := strings.ReplaceAll(instanceName, ".", "_"); underscored != instanceName {
		candidates = append(candidates, underscored)
	}
	return candidates
}

// abbreviationCandidate extracts the venue-abbreviation prefix from an instance
// name, used as the final fallback when no device match is found by any other
// identifier (IP, name, underscored name, MAC/SERIAL/JIRAKEY). Convention: the
// venue abbreviation is the segment before the first "-"
// (e.g. "HE-RAD_C5-Helena62" → "he").
func abbreviationCandidate(instanceName string) (string, bool) {
	idx := strings.Index(instanceName, "-")
	if idx <= 0 {
		return "", false
	}
	return strings.ToLower(instanceName[:idx]), true
}

// ── Jira field builder ────────────────────────────────────────────────────────

// buildJiraFields maps device meta keys → Jira custom fields formatted as "{workspaceID}:{objectID}".
// Only includes keys that are present and non-empty in the device meta.
func buildJiraFields(meta map[string]interface{}, fieldMapping map[string]string, workspaceID string) map[string]string {
	out := make(map[string]string, len(fieldMapping))
	for metaKey, customField := range fieldMapping {
		v, exists := meta[metaKey]
		if !exists || v == nil {
			continue
		}
		id := strings.TrimSpace(fmt.Sprintf("%v", v))
		if id == "" {
			continue
		}
		out[customField] = workspaceID + ":" + id
	}
	return out
}

// buildKeyJiraFields returns the asset server's pre-resolved Jira object keys
// (jira_device_key, jira_venue_key, etc.) and their human-readable names
// (jira_device_name, jira_venue_name, etc.), plus the derived upstream
// device's key/name/MAC address and the device's own MAC address, keyed by
// their own field name with the raw value (e.g. "IHS-20846" or
// "FC:11:65:B6:A3:42"). Empty/null values are omitted.
func buildKeyJiraFields(device *DeviceResponse, upstreamDeviceKey, upstreamDeviceName, upstreamDeviceMac string) map[string]string {
	out := make(map[string]string, 16)
	add := func(key, value string) {
		if value != "" {
			out[key] = value
		}
	}
	add("jira_device_key", device.JiraDeviceKey)
	add("jira_subvenue_key", device.JiraSubvenueKey)
	add("jira_location_key", device.JiraLocationKey)
	add("jira_venue_key", device.JiraVenueKey)
	add("jira_model_key", device.JiraModelKey)
	add("jira_device_name", device.JiraDeviceName)
	add("jira_subvenue_name", device.JiraSubvenueName)
	add("jira_location_name", device.JiraLocationName)
	add("jira_venue_name", device.JiraVenueName)
	add("jira_model_name", device.JiraModelName)
	add("jira_modelclass_name", device.JiraModelclassName)
	if manufacturer, ok := device.Meta["manufacturer"].(string); ok {
		add("jira_technology_name", manufacturer)
	}
	add("jira_upstream_device_key", upstreamDeviceKey)
	add("jira_upstream_device_name", upstreamDeviceName)
	add("jira_upstream_device_mac", upstreamDeviceMac)
	add("device_mac", device.MacAddress)
	return out
}

// buildVenueOnlyFields maps a venue-abbreviation match to whatever Jira fields
// can be derived from the venue alone — used when a device couldn't be
// resolved by any other identifier, so subvenue/location/device stay unknown.
func buildVenueOnlyFields(venue *VenueResponse, fieldMapping map[string]string, workspaceID string) map[string]string {
	out := make(map[string]string, 3)
	if venue.VenueID != "" {
		if customField, ok := fieldMapping["venue_id"]; ok {
			out[customField] = workspaceID + ":" + venue.VenueID
		}
	}
	if venue.VenueKey != "" {
		out["jira_venue_key"] = venue.VenueKey
	}
	if venue.VenueName != "" {
		out["jira_venue_name"] = venue.VenueName
	}
	return out
}

// ── Per-project processing ────────────────────────────────────────────────────

// assetData bundles the in-memory indexes built once per run from the asset
// server's bulk exports (GET /devices/export, /devices/edges/export,
// /venues/abbreviations), shared across every project.
type assetData struct {
	devices *deviceIndex
	edges   *edgeIndex
	venues  venueIndex
}

func processProject(
	ctx context.Context,
	project string,
	cfg *Config,
	ifClient *iflib.Client,
	assets *assetData,
	dryRun bool,
) error {
	instances, err := ifClient.ListProjectInstances(ctx, project)
	if err != nil {
		return fmt.Errorf("list instances: %w", err)
	}
	log.Printf("  %d instances", len(instances))

	// Instances with no recognized MAC/SERIAL/JIRAKEY prefix (e.g. "host.13884")
	// fall back to IP-based lookup, so pre-fetch their IP addresses in batches.
	var noPrefixNames []string
	for _, instanceName := range instances {
		if _, ok := parseIdentifier(instanceName); !ok {
			noPrefixNames = append(noPrefixNames, instanceName)
		}
	}
	ipByInstance, err := fetchInstanceIPs(ctx, ifClient, project, cfg.InsightFinder.Username, noPrefixNames, cfg.MetadataBatchSize)
	if err != nil {
		log.Printf("  WARN  IP lookup for unprefixed instances failed: %v (continuing without IP fallback)", err)
		ipByInstance = nil
	}

	var entries []iflib.ThirdPartyInstanceEntry
	var noPrefix, notFound, noIDs, abbrMatched int

	for _, instanceName := range instances {
		var candidates []string
		if identifier, ok := parseIdentifier(instanceName); ok {
			candidates = []string{identifier}
		} else {
			noPrefix++
			candidates = identifierCandidates(instanceName, ipByInstance[instanceName])
		}

		var device *DeviceResponse
		for _, candidate := range candidates {
			if d := assets.devices.find(candidate); d != nil {
				device = d
				break
			}
		}
		if device == nil {
			// Last resort: derive a venue abbreviation from the instance name
			// itself (e.g. "HE-RAD_C5-Helena62" → "he") and look up the venue
			// directly, so at least venue-level fields can be populated.
			if abbr, ok := abbreviationCandidate(instanceName); ok {
				if venue := assets.venues.find(abbr); venue != nil {
					if fields := buildVenueOnlyFields(venue, cfg.Jira.FieldMapping, cfg.Jira.WorkspaceID); len(fields) > 0 {
						abbrMatched++
						log.Printf("  ABBR  %q → venue %q (abbreviation %q) %v", instanceName, venue.VenueName, abbr, fields)
						entries = append(entries, iflib.ThirdPartyInstanceEntry{
							InstanceName: instanceName,
							JiraConfigs: iflib.ThirdPartyJiraConfigs{
								JiraIssueFields: fields,
							},
						})
						continue
					}
				}
			}
			notFound++
			log.Printf("  MISS  %q (tried %v)", instanceName, candidates)
			continue
		}

		fields := buildJiraFields(device.Meta, cfg.Jira.FieldMapping, cfg.Jira.WorkspaceID)

		var upstreamDeviceKey, upstreamDeviceName, upstreamDeviceMac string
		if upstream := assets.edges.upstream(device.ID, cfg.AssetServer.UpstreamMaxDepth, assets.devices); len(upstream) > 0 {
			upstreamDeviceKey = upstream[0].ObjectKey
			upstreamDeviceName = upstream[0].Name
			upstreamDeviceMac = upstream[0].MacAddress
		}

		for key, value := range buildKeyJiraFields(device, upstreamDeviceKey, upstreamDeviceName, upstreamDeviceMac) {
			fields[key] = value
		}

		if len(fields) == 0 {
			noIDs++
			log.Printf("  NOID  %q → %s (no venue IDs in meta yet)", instanceName, device.ObjectKey)
			continue
		}

		log.Printf("  OK    %q → %s %v", instanceName, device.ObjectKey, fields)
		entries = append(entries, iflib.ThirdPartyInstanceEntry{
			InstanceName: instanceName,
			JiraConfigs: iflib.ThirdPartyJiraConfigs{
				JiraIssueFields: fields,
			},
		})
	}

	log.Printf("  ready=%d  no-prefix-fallback=%d  abbreviation-fallback=%d  not-found=%d  no-ids=%d",
		len(entries), noPrefix, abbrMatched, notFound, noIDs)

	if len(entries) == 0 {
		return nil
	}

	if dryRun {
		b, _ := json.MarshalIndent(entries, "    ", "  ")
		log.Printf("  [dry-run] would upload:\n    %s", string(b))
		return nil
	}

	if err := ifClient.UploadThirdPartyInstanceMetadata(ctx, project, entries); err != nil {
		return fmt.Errorf("upload: %w", err)
	}
	log.Printf("  uploaded %d entries", len(entries))
	return nil
}

// ── Main ──────────────────────────────────────────────────────────────────────

func main() {
	configPath := flag.String("config", "config.yaml", "path to YAML config file")
	dryRun := flag.Bool("dry-run", false, "print payloads without uploading to InsightFinder")
	flag.Parse()

	cfg, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	if err := validateConfig(cfg); err != nil {
		log.Fatalf("config validation: %v", err)
	}

	ctx := context.Background()

	ifClient, err := iflib.New(
		cfg.InsightFinder.URL,
		cfg.InsightFinder.Username,
		cfg.InsightFinder.LicenseKey,
		cfg.InsightFinder.Password,
		iflib.WithInsecureSkipVerify(),
		iflib.WithRetry(3, 5*time.Second),
	)
	if err != nil {
		log.Fatalf("create IF client: %v", err)
	}

	client := newAssetClient(cfg.AssetServer.URL, cfg.AssetServer.APIKey)

	// Bulk-fetch once for the whole run — shared across every project below —
	// instead of one HTTP round trip per instance.
	t0 := time.Now()
	rawDevices, err := client.exportDevices(ctx)
	if err != nil {
		log.Fatalf("export devices: %v", err)
	}
	rawEdges, err := client.exportEdges(ctx)
	if err != nil {
		log.Fatalf("export edges: %v", err)
	}
	rawVenues, err := client.exportVenueAbbreviations(ctx)
	if err != nil {
		log.Fatalf("export venue abbreviations: %v", err)
	}
	log.Printf("fetched %d devices, %d edges, %d venue abbreviations in %s",
		len(rawDevices), len(rawEdges), len(rawVenues), time.Since(t0).Round(time.Millisecond))

	assets := &assetData{
		devices: newDeviceIndex(rawDevices),
		edges:   newEdgeIndex(rawEdges),
		venues:  newVenueIndex(rawVenues),
	}

	if *dryRun {
		log.Println("--- DRY RUN: no data will be sent to InsightFinder ---")
	}

	for _, project := range cfg.Projects {
		log.Printf("=== %s ===", project)
		if err := processProject(ctx, project, cfg, ifClient, assets, *dryRun); err != nil {
			log.Printf("ERROR [%s]: %v", project, err)
		}
	}
}
