// upload-deps — generate AP parent/child dependency relations directly from the
// asset server's device/edge data and upsert them into an InsightFinder causal
// dependency map.
//
// Once per run, it bulk-fetches every device and dependency edge from the
// AccessParks asset server (GET /devices/export, /devices/edges/export) and
// builds in-memory indexes — one HTTP round trip per dataset instead of one
// per instance, since a run resolves upstream relations for every instance
// across every configured project.
//
// Flow (for every configured project):
//  1. List all instance names for the project.
//  2. Resolve each instance name to an asset-server identifier (MAC/SERIAL/JIRAKEY
//     prefix, same convention as getmessages_zabbix.py; unprefixed names fall back
//     to IP lookup, then the raw/underscored instance name).
//  3. Resolve the identifier against the local device index and walk the local
//     edge index to find the immediate parent device(s) (mirrors the asset
//     server's GET /devices/{id}/upstream), building an instance name for each
//     parent the same way (MAC > SERIAL > JIRAKEY), and reading its zone from
//     meta.venue.
//
//     If the immediate (depth-1) parent's manufacturer/model matches a
//     configured "passthrough_devices" entry (e.g. Tarana BN, Positron
//     G1001-C G.hnEndPoint — passive hardware that is never itself a
//     monitored instance), the depth-2 device from the same lookup is ALSO
//     wired up as a parent of the instance. Both candidate pairs are kept;
//     whichever parent isn't a known monitored instance is dropped in the
//     validation pass below, so the instance still ends up with a working
//     relation once the unmonitored passthrough device is filtered out.
//
// Once every project has been processed, all candidate pairs are validated
// against the combined instance set of ALL configured projects (a parent may
// live in a different project than its child), grouped by zone, and upserted
// into the single shared causal group in one final pass — existing relations
// for other source/target pairs are preserved.
//
// freshOnly mode (set "fresh_only: true" in config):
//
//	Before uploading each zone, fetches the current dependency map and drops any
//	candidate pairs whose source→target already exists. Only genuinely new pairs
//	are sent. Existing relations are always preserved regardless of this setting.
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
	"unicode"

	"github.com/insightfinder/InsightAgent/iflib"
	"gopkg.in/yaml.v3"
)

// ── Config ────────────────────────────────────────────────────────────────────

type Config struct {
	InsightFinder     IFConfig    `yaml:"insightfinder"`
	AssetServer       AssetConfig `yaml:"asset_server"`
	CausalKey         string      `yaml:"causal_key"`
	Projects          []string    `yaml:"projects"`
	FreshOnly         bool        `yaml:"fresh_only"`
	MaxWorkers        int         `yaml:"max_workers"`
	MetadataBatchSize int         `yaml:"metadata_batch_size"`
	// DebugOutputFile is where the final validated parent/child relations are
	// dumped as JSON (with source project and InsightFinder display name for
	// both ends of every relation), for local debugging/search. Written on
	// every run, including -dry-run. Defaults to "relations_debug.json".
	DebugOutputFile string `yaml:"debug_output_file"`
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
	// PassthroughDevices lists manufacturer/model pairs that are treated as
	// passive/unmonitored pass-through hardware. When an instance's immediate
	// (depth-1) upstream device matches one of these, the depth-2 device found
	// in the same upstream lookup is ALSO wired directly to the instance as a
	// parent, in addition to the normal depth-1 parent relation.
	PassthroughDevices []PassthroughDevice `yaml:"passthrough_devices"`
}

// PassthroughDevice identifies a manufacturer/model pair (e.g. a Tarana BN
// bridge or a Positron G.hn endpoint) that sits immediately upstream of a
// monitored device but is never itself the monitored/instance target for a
// causal relation. Comparisons are case-insensitive.
type PassthroughDevice struct {
	Manufacturer string `yaml:"manufacturer"`
	ModelName    string `yaml:"model_name"`
}

// matchesPassthrough reports whether (manufacturer, modelName) matches any
// configured passthrough rule, case-insensitively.
func matchesPassthrough(manufacturer, modelName string, rules []PassthroughDevice) bool {
	for _, r := range rules {
		if strings.EqualFold(manufacturer, r.Manufacturer) && strings.EqualFold(modelName, r.ModelName) {
			return true
		}
	}
	return false
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
	if cfg.InsightFinder.Password == "" {
		return fmt.Errorf("insightfinder.password is required (causal endpoints use session auth)")
	}
	if cfg.AssetServer.URL == "" {
		return fmt.Errorf("asset_server.url is required")
	}
	if cfg.AssetServer.APIKey == "" {
		return fmt.Errorf("asset_server.api_key is required")
	}
	if cfg.CausalKey == "" {
		return fmt.Errorf("causal_key is required")
	}
	if len(cfg.Projects) == 0 {
		return fmt.Errorf("projects list is empty")
	}
	if cfg.AssetServer.UpstreamMaxDepth <= 0 {
		cfg.AssetServer.UpstreamMaxDepth = 1
	}
	if cfg.MaxWorkers <= 0 {
		cfg.MaxWorkers = 20
	}
	if cfg.MetadataBatchSize <= 0 {
		cfg.MetadataBatchSize = 500
	}
	if cfg.DebugOutputFile == "" {
		cfg.DebugOutputFile = "relations_debug.json"
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
		// This client now makes exactly 2 bulk-export requests per run rather
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
	Model        *struct {
		Name         string `json:"name"`
		Manufacturer string `json:"manufacturer"`
	} `json:"model"`
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
	ID           string
	Name         string
	ObjectKey    string
	MacAddress   string
	SerialNumber string
	Depth        int
	Manufacturer string
	ModelName    string
	Meta         map[string]interface{}
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
		u := UpstreamDevice{
			ID: d.ID, Name: d.Name, ObjectKey: d.ObjectKey,
			MacAddress: d.MacAddress, SerialNumber: d.SerialNumber,
			Depth: depthOf[id], Meta: d.Meta,
		}
		if d.Model != nil {
			u.Manufacturer = d.Model.Manufacturer
			u.ModelName = d.Model.Name
		}
		out = append(out, u)
	}
	return out
}

// assetData bundles the in-memory indexes built once per run from the asset
// server's bulk exports (GET /devices/export, /devices/edges/export), shared
// across every project.
type assetData struct {
	devices *deviceIndex
	edges   *edgeIndex
}

// ── Instance name parsing ─────────────────────────────────────────────────────
//
// Recognized instance-name prefixes (set by getmessages_zabbix.py):
//
//	"MAC "     → MAC address, e.g. "4C:B1:CD:38:3C:60"
//	"SERIAL "  → serial number, e.g. "ABC123SS"
//	"JIRAKEY " → Jira object key, e.g. "IHS-23344"

// parseIdentifier strips the InsightFinder identifier prefix from an instance name
// and returns the raw value to use for an asset server lookup.
// Returns ("", false) when no prefix is found.
func parseIdentifier(instanceName string) (identifier string, ok bool) {
	switch {
	case strings.HasPrefix(instanceName, "MAC "):
		// Instance names store MACs with dashes (e.g. "18-4B-0D-13-C3-70");
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

// hasAlnum reports whether s contains at least one letter or digit.
func hasAlnum(s string) bool {
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return true
		}
	}
	return false
}

// makeInstanceName builds an InsightFinder instance name from raw device fields,
// mirroring the effective_in logic in getmessages_zabbix.py: MAC > SERIAL > JIRAKEY.
func makeInstanceName(macAddress, serialNumber, objectKey string) (string, bool) {
	if macAddress != "" {
		candidate := strings.TrimSpace(strings.Trim(strings.ReplaceAll(macAddress, ":", "-"), "-"))
		if candidate != "" && hasAlnum(candidate) {
			return "MAC " + candidate, true
		}
	}
	if serialNumber != "" && hasAlnum(serialNumber) {
		return "SERIAL " + serialNumber, true
	}
	if objectKey != "" && hasAlnum(objectKey) {
		return "JIRAKEY " + objectKey, true
	}
	return "", false
}

// ── Relation candidates ───────────────────────────────────────────────────────

// relationCandidate is one parent→child pair discovered from the asset server,
// not yet validated against the combined instance set.
type relationCandidate struct {
	Parent string
	Child  string
	Zone   string
}

// relationDebugEntry is one validated, deduped parent→child relation enriched
// with debugging context, dumped to Config.DebugOutputFile every run.
type relationDebugEntry struct {
	Child               string `json:"child"`
	Parent              string `json:"parent"`
	Zone                string `json:"zone"`
	ChildSourceProject  string `json:"child_source_project"`
	ParentSourceProject string `json:"parent_source_project"`
	ChildDisplayName    string `json:"child_display_name"`
	ParentDisplayName   string `json:"parent_display_name"`
}

// resolveProjectRelations discovers parent/child relation candidates for every
// instance in a project using the asset server's bulk-fetched device/edge indexes.
func resolveProjectRelations(
	ctx context.Context,
	project string,
	instances []string,
	ifClient *iflib.Client,
	assets *assetData,
	cfg *Config,
) []relationCandidate {
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

	// When passthrough rules are configured, we need visibility into depth-2
	// devices to wire them up as an extra parent, even if the configured
	// max_depth is shallower.
	queryDepth := cfg.AssetServer.UpstreamMaxDepth
	if len(cfg.AssetServer.PassthroughDevices) > 0 && queryDepth < 2 {
		queryDepth = 2
	}

	// Resolution is now pure in-memory index lookups (no I/O), so a plain loop
	// replaces what used to be a worker pool spreading out HTTP round trips.
	var candidates []relationCandidate
	for _, instanceName := range instances {
		rels := resolveInstanceRelations(instanceName, ipByInstance[instanceName], assets, queryDepth, cfg.AssetServer.PassthroughDevices)
		candidates = append(candidates, rels...)
	}
	return candidates
}

// resolveInstanceRelations finds the parent(s) of a single instance via the local
// device/edge indexes, trying identifier candidates in order until one resolves.
//
// Normally only the depth-1 (immediate upstream) device becomes a parent relation.
// If the depth-1 device matches one of passthroughDevices (e.g. a Tarana BN bridge
// or Positron G.hn endpoint that is never itself a monitored instance), the depth-2
// device from the same lookup is ALSO wired up as a parent, so the instance still
// gets a valid relation once the unmonitored depth-1 device is filtered out during
// instance-set validation.
func resolveInstanceRelations(instanceName, ip string, assets *assetData, maxDepth int, passthroughDevices []PassthroughDevice) []relationCandidate {
	var candidates []string
	if identifier, ok := parseIdentifier(instanceName); ok {
		candidates = []string{identifier}
	} else {
		candidates = identifierCandidates(instanceName, ip)
	}

	var device *DeviceResponse
	for _, candidate := range candidates {
		if d := assets.devices.find(candidate); d != nil {
			device = d
			break
		}
	}
	if device == nil {
		return nil
	}

	upstream := assets.edges.upstream(device.ID, maxDepth, assets.devices)
	if len(upstream) == 0 {
		return nil
	}

	var depth1, depth2 []UpstreamDevice
	for _, d := range upstream {
		switch d.Depth {
		case 1:
			depth1 = append(depth1, d)
		case 2:
			depth2 = append(depth2, d)
		}
	}

	passthroughMatched := false
	for _, d := range depth1 {
		if matchesPassthrough(d.Manufacturer, d.ModelName, passthroughDevices) {
			passthroughMatched = true
			break
		}
	}

	var rels []relationCandidate
	addRel := func(parent UpstreamDevice) {
		parentName, ok := makeInstanceName(parent.MacAddress, parent.SerialNumber, parent.ObjectKey)
		if !ok {
			return
		}
		var zone string
		if parent.Meta != nil {
			if v, ok := parent.Meta["venue"].(string); ok {
				zone = v
			}
		}
		rels = append(rels, relationCandidate{Parent: parentName, Child: instanceName, Zone: zone})
	}

	for _, parent := range depth1 {
		addRel(parent)
	}
	if passthroughMatched {
		for _, parent := range depth2 {
			addRel(parent)
		}
	}
	return rels
}

// ── Main ──────────────────────────────────────────────────────────────────────

func main() {
	configPath := flag.String("config", "config.yaml", "path to YAML config file")
	dryRun := flag.Bool("dry-run", false, "resolve and print candidate relations without uploading to InsightFinder")
	flag.Parse()

	cfg, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	if err := validateConfig(cfg); err != nil {
		log.Fatalf("config validation: %v", err)
	}

	ctx := context.Background()

	client, err := iflib.New(
		cfg.InsightFinder.URL,
		cfg.InsightFinder.Username,
		cfg.InsightFinder.LicenseKey,
		cfg.InsightFinder.Password,
		iflib.WithInsecureSkipVerify(),
		iflib.WithRetry(3, 5*time.Second),
	)
	if err != nil {
		log.Fatalf("create client: %v", err)
	}

	assetHTTPClient := newAssetClient(cfg.AssetServer.URL, cfg.AssetServer.APIKey)

	// Bulk-fetch once for the whole run — shared across every project below —
	// instead of one HTTP round trip per instance.
	t0 := time.Now()
	rawDevices, err := assetHTTPClient.exportDevices(ctx)
	if err != nil {
		log.Fatalf("export devices: %v", err)
	}
	rawEdges, err := assetHTTPClient.exportEdges(ctx)
	if err != nil {
		log.Fatalf("export edges: %v", err)
	}
	log.Printf("fetched %d devices, %d edges in %s",
		len(rawDevices), len(rawEdges), time.Since(t0).Round(time.Millisecond))

	assets := &assetData{
		devices: newDeviceIndex(rawDevices),
		edges:   newEdgeIndex(rawEdges),
	}

	if *dryRun {
		log.Println("--- DRY RUN: no data will be sent to InsightFinder ---")
	}

	// ── Step 1: list instances for every project, building the combined set ────

	instanceSet := map[string]struct{}{}
	// instanceProject and displayNameByInstance track which project each instance
	// came from and its InsightFinder display name, keyed by raw instance name —
	// used only to enrich the local debug JSON dump, not for relation resolution.
	instanceProject := map[string]string{}
	displayNameByInstance := map[string]string{}
	var allCandidates []relationCandidate

	for _, project := range cfg.Projects {
		log.Printf("=== %s ===", project)

		instances, err := client.ListInstances(ctx, project)
		if err != nil {
			log.Printf("  ERROR list instances: %v", err)
			continue
		}
		log.Printf("  %d instances", len(instances))
		for _, name := range instances {
			instanceSet[name] = struct{}{}
			if _, exists := instanceProject[name]; !exists {
				instanceProject[name] = project
			}
		}

		displayNames, err := client.GetInstanceDisplayNames(ctx, project, cfg.InsightFinder.Username)
		if err != nil {
			log.Printf("  WARN  display name lookup failed: %v (debug dump will fall back to instance names)", err)
		} else {
			for _, d := range displayNames {
				for _, instName := range d.InstanceSet {
					if _, exists := displayNameByInstance[instName]; !exists {
						displayNameByInstance[instName] = d.DisplayName
					}
				}
			}
		}

		candidates := resolveProjectRelations(ctx, project, instances, client, assets, cfg)
		log.Printf("  %d candidate relation(s) discovered", len(candidates))
		allCandidates = append(allCandidates, candidates...)
	}

	displayNameFor := func(instanceName string) string {
		if v, ok := displayNameByInstance[instanceName]; ok && v != "" {
			return v
		}
		return instanceName
	}

	log.Printf("Discovered %d candidate relation(s) across %d project(s)", len(allCandidates), len(cfg.Projects))

	// ── Step 2: validate against the combined instance set, group by zone ──────

	type zoneRelations struct {
		zone      string
		relations []iflib.DependencyRelation
	}

	zoneOrder := []string{}
	zoneMap := map[string]*zoneRelations{}
	seenPair := map[string]struct{}{}
	var debugEntries []relationDebugEntry

	skipped, duplicates := 0, 0
	for _, cand := range allCandidates {
		_, parentOK := instanceSet[cand.Parent]
		_, childOK := instanceSet[cand.Child]
		if !parentOK || !childOK {
			skipped++
			continue
		}

		pairKey := cand.Parent + "→" + cand.Child
		if _, dup := seenPair[pairKey]; dup {
			duplicates++
			continue
		}
		seenPair[pairKey] = struct{}{}

		dr := iflib.BuildRelation(cand.Parent, cand.Child, "instanceLevel", iflib.RelationConfirmed)

		if _, exists := zoneMap[cand.Zone]; !exists {
			zoneOrder = append(zoneOrder, cand.Zone)
			zoneMap[cand.Zone] = &zoneRelations{zone: cand.Zone}
		}
		zoneMap[cand.Zone].relations = append(zoneMap[cand.Zone].relations, dr)

		debugEntries = append(debugEntries, relationDebugEntry{
			Child:               cand.Child,
			Parent:              cand.Parent,
			Zone:                cand.Zone,
			ChildSourceProject:  instanceProject[cand.Child],
			ParentSourceProject: instanceProject[cand.Parent],
			ChildDisplayName:    displayNameFor(cand.Child),
			ParentDisplayName:   displayNameFor(cand.Parent),
		})
	}

	valid := len(allCandidates) - skipped - duplicates
	log.Printf("Valid pairs: %d / %d (skipped %d with missing instances, %d duplicates)",
		valid, len(allCandidates), skipped, duplicates)

	if b, err := json.MarshalIndent(debugEntries, "", "  "); err != nil {
		log.Printf("  WARN  failed to marshal debug relations: %v", err)
	} else if err := os.WriteFile(cfg.DebugOutputFile, b, 0644); err != nil {
		log.Printf("  WARN  failed to write debug relations to %q: %v", cfg.DebugOutputFile, err)
	} else {
		log.Printf("Wrote %d relation(s) to debug file %q", len(debugEntries), cfg.DebugOutputFile)
	}

	if valid == 0 {
		log.Println("No valid pairs to upload — exiting.")
		return
	}

	if *dryRun {
		for _, zoneName := range zoneOrder {
			zr := zoneMap[zoneName]
			b, _ := json.MarshalIndent(zr.relations, "  ", "  ")
			log.Printf("  [dry-run] zone %q (%d relation(s)):\n  %s", zoneName, len(zr.relations), string(b))
		}
		return
	}

	// ── Step 3: upsert per zone into the shared causal group ────────────────────
	// This runs once, after every project has been processed, so relations from
	// different projects that share a zone are combined before upload.

	totalUploaded := 0
	for _, zoneName := range zoneOrder {
		zr := zoneMap[zoneName]
		candidates := zr.relations

		if cfg.FreshOnly {
			existing, err := client.GetDependencyRelations(ctx, cfg.CausalKey, zr.zone)
			if err != nil {
				log.Printf("  ERROR fetching existing relations for zone %q: %v — skipping zone", zr.zone, err)
				continue
			}

			existingSet := make(map[string]struct{}, len(existing))
			for _, r := range existing {
				if len(r.Sources) > 0 && len(r.Targets) > 0 {
					existingSet[r.Sources[0].ID+"→"+r.Targets[0].ID] = struct{}{}
				}
			}

			var fresh []iflib.DependencyRelation
			for _, r := range candidates {
				key := r.Sources[0].ID + "→" + r.Targets[0].ID
				if _, exists := existingSet[key]; exists {
					continue
				}
				fresh = append(fresh, r)
			}

			log.Printf("Zone %q: %d candidate(s), %d already exist, %d new to upload",
				zr.zone, len(candidates), len(candidates)-len(fresh), len(fresh))

			if len(fresh) == 0 {
				log.Printf("  Nothing new for zone %q — skipping.", zr.zone)
				continue
			}
			candidates = fresh
		}

		log.Printf("Upserting %d relation(s) into causal group %q zone %q (existing relations preserved)...",
			len(candidates), cfg.CausalKey, zr.zone)

		if err := client.UpsertDependencyRelations(ctx, cfg.CausalKey, zr.zone, candidates); err != nil {
			log.Printf("  ERROR zone %q: %v", zr.zone, err)
			continue
		}
		log.Printf("  Done — zone %q updated.", zr.zone)
		totalUploaded += len(candidates)
	}

	log.Printf("Finished. Uploaded %d relation(s) across %d zone(s).", totalUploaded, len(zoneOrder))
}
