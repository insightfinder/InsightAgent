// venue-ids — set Jira venue/subvenue/location/device IDs on InsightFinder instances.
//
// For each configured project it:
//  1. Lists all instances from InsightFinder.
//  2. Strips the "MAC ", "SERIAL ", or "JIRAKEY " prefix from each instance name to
//     obtain the raw identifier (e.g. "4C:B1:CD:38:3C:60", "IHS-23344", "ABC123SS").
//     Instances with none of these prefixes (e.g. "host.13884") fall back to: the
//     instance's IP address, then the instance name as-is, then the instance name
//     with "." replaced by "_".
//  3. Queries the AccessParks asset server GET /devices/{identifier}.
//  4. Reads venue_id, subvenue_id, location_id, device_id from the device meta.
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
	"net/url"
	"os"
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
		baseURL:    strings.TrimRight(baseURL, "/"),
		apiKey:     apiKey,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

// DeviceResponse mirrors the GET /devices/{id} response from the asset server.
type DeviceResponse struct {
	ID         string                 `json:"id"`
	ObjectKey  string                 `json:"object_key"`
	Name       string                 `json:"name"`
	DeviceName string                 `json:"device_name"`
	Meta       map[string]interface{} `json:"meta"`

	// Pre-resolved Jira object keys (e.g. "IHS-20846"). May be null/empty when
	// the corresponding Jira object hasn't been created yet.
	JiraDeviceKey   string `json:"jira_device_key"`
	JiraLocationKey string `json:"jira_location_key"`
	JiraSubvenueKey string `json:"jira_subvenue_key"`
	JiraVenueKey    string `json:"jira_venue_key"`
	JiraModelKey    string `json:"jira_model_key"`
}

// UpstreamDevice mirrors one entry of the GET /devices/{id}/upstream response.
type UpstreamDevice struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	ObjectKey string `json:"object_key"`
	Depth     int    `json:"depth"`
}

func (a *assetClient) lookup(ctx context.Context, identifier string) (*DeviceResponse, error) {
	endpoint := fmt.Sprintf("%s/devices/%s", a.baseURL, url.PathEscape(identifier))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-API-Key", a.apiKey)
	req.Header.Set("Accept", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var device DeviceResponse
	if err := json.NewDecoder(resp.Body).Decode(&device); err != nil {
		return nil, fmt.Errorf("decode: %w", err)
	}
	return &device, nil
}

// lookupUpstream calls GET /devices/{identifier}/upstream?max_depth={maxDepth}
// and returns the upstream device chain (nearest first).
func (a *assetClient) lookupUpstream(ctx context.Context, identifier string, maxDepth int) ([]UpstreamDevice, error) {
	endpoint := fmt.Sprintf("%s/devices/%s/upstream?max_depth=%d", a.baseURL, url.PathEscape(identifier), maxDepth)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-API-Key", a.apiKey)
	req.Header.Set("Accept", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var upstream []UpstreamDevice
	if err := json.NewDecoder(resp.Body).Decode(&upstream); err != nil {
		return nil, fmt.Errorf("decode: %w", err)
	}
	return upstream, nil
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
// (jira_device_key, jira_venue_key, etc.) plus the derived upstream device key,
// keyed by their own field name with the raw Jira key value (e.g. "IHS-20846").
// Empty/null values are omitted.
func buildKeyJiraFields(device *DeviceResponse, upstreamDeviceKey string) map[string]string {
	out := make(map[string]string, 6)
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
	add("jira_upstream_device_key", upstreamDeviceKey)
	return out
}

// ── Per-project processing ────────────────────────────────────────────────────

func processProject(
	ctx context.Context,
	project string,
	cfg *Config,
	ifClient *iflib.Client,
	assets *assetClient,
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
	var noPrefix, notFound, noIDs int

	for _, instanceName := range instances {
		var candidates []string
		if identifier, ok := parseIdentifier(instanceName); ok {
			candidates = []string{identifier}
		} else {
			noPrefix++
			candidates = identifierCandidates(instanceName, ipByInstance[instanceName])
		}

		var device *DeviceResponse
		var identifier string
		for _, candidate := range candidates {
			d, err := assets.lookup(ctx, candidate)
			if err != nil {
				log.Printf("  WARN  %q → lookup error for %q: %v", instanceName, candidate, err)
				continue
			}
			if d != nil {
				device, identifier = d, candidate
				break
			}
		}
		if device == nil {
			notFound++
			log.Printf("  MISS  %q (tried %v)", instanceName, candidates)
			continue
		}

		fields := buildJiraFields(device.Meta, cfg.Jira.FieldMapping, cfg.Jira.WorkspaceID)

		var upstreamDeviceKey string
		upstream, err := assets.lookupUpstream(ctx, identifier, cfg.AssetServer.UpstreamMaxDepth)
		if err != nil {
			log.Printf("  WARN  %q → upstream lookup error: %v", instanceName, err)
		} else if len(upstream) > 0 {
			upstreamDeviceKey = upstream[0].ObjectKey
		}

		for key, value := range buildKeyJiraFields(device, upstreamDeviceKey) {
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

	log.Printf("  ready=%d  no-prefix-fallback=%d  not-found=%d  no-ids=%d",
		len(entries), noPrefix, notFound, noIDs)

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

	assets := newAssetClient(cfg.AssetServer.URL, cfg.AssetServer.APIKey)

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
