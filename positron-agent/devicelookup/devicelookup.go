// Package devicelookup enriches devices with data from the Device Inventory /
// Asset Registry API, keyed by MAC address, serial number, or device name
// (first match wins). Same API and lookup convention used by the mimosa,
// netexperience, tarana-gnmic, and baicells agents, so the same physical
// device resolves to the same InsightFinder instance identity across agents.
//
// Field priority follows the baicells-agent convention specifically:
//   - Instance name: Inventory MAC > Inventory serial > Inventory object key >
//     the device's own name (cleaned). If none of these are available, the
//     caller must drop the device rather than send it under any other
//     fallback identifier.
//   - Display name: always the device's own raw name (uncleaned) - never
//     falls back to the Inventory's name field.
//   - Component name / Zone: Inventory only, no default value - omitted
//     entirely if Inventory doesn't have them.
//   - IP: Inventory ip_address > the device's own reported IP.
//   - No case conversion anywhere.
package devicelookup

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	neturl "net/url"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode"

	config "github.com/insightfinder/positron-agent/configs"
	"github.com/sirupsen/logrus"
)

const lookupPath = "devicelookup.json"
const notFoundPath = "devicelookup_notfound.json"
const lookupConcurrency = 20

// DeviceInfo holds the fields we need from the device inventory API response.
type DeviceInfo struct {
	SerialNumber  string `json:"serial_number"`
	ObjectKey     string `json:"object_key"`
	MACAddress    string `json:"mac_address"`
	Name          string `json:"name"`
	Venue         string `json:"venue"`
	ComponentName string `json:"component_name"`
	IPAddress     string `json:"ip_address"`
}

// Entry caches one device lookup result.
type Entry struct {
	IdentifierUsed string     `json:"identifier_used"`
	Device         DeviceInfo `json:"device"`
}

// Lookup is a cache keyed by whichever identifier (MAC, serial, or name)
// resolved the device during the last refresh.
type Lookup map[string]Entry

// Identifiers is one device's set of candidate lookup keys, in priority order.
type Identifiers struct {
	// MAC is normalized (":" -> "-") for use as the cache key / instance
	// name, matching the baicells-agent convention. NOT used for the live
	// Inventory API query - the Inventory stores/matches MACs in their
	// original ":"-separated form, so a dash-normalized identifier 404s.
	// See RawMAC.
	MAC    string
	Serial string
	Name   string
	// RawMAC is the device's MAC as originally reported (not normalized,
	// colons intact) - used only for the live Inventory API query, see
	// MAC's doc comment.
	RawMAC string
}

// Load reads devicelookup.json from disk; returns an empty Lookup if absent or invalid.
func Load() Lookup {
	data, err := os.ReadFile(lookupPath)
	if err != nil {
		if !os.IsNotExist(err) {
			logrus.Warnf("DeviceLookup: failed to read %s: %v", lookupPath, err)
		}
		return make(Lookup)
	}
	var dl Lookup
	if err := json.Unmarshal(data, &dl); err != nil {
		logrus.Warnf("DeviceLookup: failed to parse %s, starting fresh: %v", lookupPath, err)
		return make(Lookup)
	}
	logrus.Infof("DeviceLookup: loaded %d entries from disk", len(dl))
	return dl
}

// IsStale reports whether devicelookup.json is missing or older than refreshHours.
func IsStale(refreshHours int) bool {
	info, err := os.Stat(lookupPath)
	if err != nil {
		return true
	}
	return time.Since(info.ModTime()) >= time.Duration(refreshHours)*time.Hour
}

// GetDeviceInfo tries each candidate key (in the order given - typically
// MAC, then serial, then name) and returns the first cache hit.
func (dl Lookup) GetDeviceInfo(candidates ...string) DeviceInfo {
	if dl == nil {
		return DeviceInfo{}
	}
	for _, c := range candidates {
		if c == "" {
			continue
		}
		if entry, ok := dl[c]; ok {
			return entry.Device
		}
	}
	return DeviceInfo{}
}

// IsResolved reports whether any candidate key already has a cache entry.
// Used to detect devices that have never gone through an inventory lookup,
// independent of whether the cache as a whole is stale - a device seen for
// the first time must be looked up immediately, not only once the next
// scheduled refresh happens to come around.
func (dl Lookup) IsResolved(candidates ...string) bool {
	for _, c := range candidates {
		if c == "" {
			continue
		}
		if _, ok := dl[c]; ok {
			return true
		}
	}
	return false
}

// Key returns the dedup key Refresh/NotFoundCache use for one device: the
// first non-empty of MAC, serial, name, in that priority order.
func Key(mac, serial, name string) string {
	return firstNonEmpty(mac, serial, name)
}

// NotFoundCache remembers which identifier keys came back not-found from
// the inventory API. It lets the incremental ("new/unresolved devices")
// refresh skip devices that genuinely don't exist in the inventory instead
// of re-querying all of them every collection cycle - they're only retried
// once the next full refresh runs, which also rebuilds this cache from
// scratch.
type NotFoundCache map[string]bool

// LoadNotFound reads devicelookup_notfound.json from disk; returns an empty
// cache if absent or invalid.
func LoadNotFound() NotFoundCache {
	data, err := os.ReadFile(notFoundPath)
	if err != nil {
		if !os.IsNotExist(err) {
			logrus.Warnf("DeviceLookup: failed to read %s: %v", notFoundPath, err)
		}
		return make(NotFoundCache)
	}
	var nf NotFoundCache
	if err := json.Unmarshal(data, &nf); err != nil {
		logrus.Warnf("DeviceLookup: failed to parse %s, starting fresh: %v", notFoundPath, err)
		return make(NotFoundCache)
	}
	return nf
}

// SaveNotFound persists the not-found cache to disk.
func SaveNotFound(nf NotFoundCache) {
	atomicWriteJSON(notFoundPath, nf)
}

// IsKnownNotFound reports whether any candidate key already came back
// not-found on a previous incremental refresh since the last full refresh.
func (nf NotFoundCache) IsKnownNotFound(candidates ...string) bool {
	for _, c := range candidates {
		if c == "" {
			continue
		}
		if nf[c] {
			return true
		}
	}
	return false
}

// ── Venue abbreviation lookup ────────────────────────────────────────────────
// Last-resort Zone fallback for devices the inventory lookup above never
// matched at all (DeviceInfo.Venue empty): venue names follow a
// "<ABBR>-<rest>" naming convention (e.g. "MEAD-LMRV-RAD_C5-Res-Budgett-1253"),
// so the segment before the first "-" in the device's own name is looked up
// against every registered venue abbreviation. Same convention used by the
// jira-metadata and mimosa agents.

const venueAbbrLookupPath = "venue_abbreviations.json"

// VenueAbbrLookup maps a lowercased venue abbreviation to its venue name.
type VenueAbbrLookup map[string]string

// LoadVenueAbbrLookup reads venue_abbreviations.json from disk; returns an
// empty lookup if absent or invalid.
func LoadVenueAbbrLookup() VenueAbbrLookup {
	data, err := os.ReadFile(venueAbbrLookupPath)
	if err != nil {
		if !os.IsNotExist(err) {
			logrus.Warnf("VenueAbbrLookup: failed to read %s: %v", venueAbbrLookupPath, err)
		}
		return make(VenueAbbrLookup)
	}
	var va VenueAbbrLookup
	if err := json.Unmarshal(data, &va); err != nil {
		logrus.Warnf("VenueAbbrLookup: failed to parse %s, starting fresh: %v", venueAbbrLookupPath, err)
		return make(VenueAbbrLookup)
	}
	logrus.Infof("VenueAbbrLookup: loaded %d entries from disk", len(va))
	return va
}

// IsVenueAbbrLookupStale reports whether venue_abbreviations.json is missing
// or older than refreshHours.
func IsVenueAbbrLookupStale(refreshHours int) bool {
	info, err := os.Stat(venueAbbrLookupPath)
	if err != nil {
		return true
	}
	return time.Since(info.ModTime()) >= time.Duration(refreshHours)*time.Hour
}

// RefreshVenueAbbrLookup bulk-fetches every abbreviation -> venue mapping
// from the Device Inventory API in one call (already cached server-side) and
// returns it, or nil if the API is unreachable/misconfigured or the request
// ultimately fails, so the caller can keep the existing lookup.
func RefreshVenueAbbrLookup(cfg config.DeviceInventoryConfig) VenueAbbrLookup {
	if cfg.APIKey == "" || cfg.BaseURL == "" {
		return nil
	}
	client := &http.Client{Timeout: time.Duration(cfg.TimeoutSec) * time.Second}
	retryDelay := time.Duration(cfg.RetryDelayMs) * time.Millisecond
	url := cfg.BaseURL + "/venues/abbreviations"

	for attempt := 1; attempt <= cfg.MaxRetry; attempt++ {
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			return nil
		}
		req.Header.Set("X-API-Key", cfg.APIKey)
		req.Header.Set("Accept", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			if attempt < cfg.MaxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil || resp.StatusCode != http.StatusOK {
			if attempt < cfg.MaxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}

		var venues []struct {
			Abbreviation string `json:"abbreviation"`
			VenueName    string `json:"venue_name"`
		}
		if err := json.Unmarshal(body, &venues); err != nil {
			logrus.Warnf("VenueAbbrLookup: failed to decode response: %v", err)
			return nil
		}
		va := make(VenueAbbrLookup, len(venues))
		for _, v := range venues {
			if v.Abbreviation != "" && v.VenueName != "" {
				va[strings.ToLower(v.Abbreviation)] = v.VenueName
			}
		}
		if len(va) == 0 {
			logrus.Warn("VenueAbbrLookup: refresh returned 0 mappings, keeping previous lookup")
			return nil
		}
		logrus.Infof("VenueAbbrLookup: refreshed %d abbreviation mappings", len(va))
		return va
	}
	logrus.Warn("VenueAbbrLookup: refresh failed, keeping existing lookup")
	return nil
}

// SaveVenueAbbrLookup persists the venue abbreviation lookup to disk.
func SaveVenueAbbrLookup(va VenueAbbrLookup) {
	atomicWriteJSON(venueAbbrLookupPath, va)
}

// AbbreviationCandidate extracts the venue-abbreviation prefix from a
// device's own name: the segment before the first "-" (e.g.
// "MEAD-LMRV-RAD_C5-Res-Budgett-1253" -> "mead"). Returns "" if there's no
// "-" or nothing precedes it.
func AbbreviationCandidate(name string) string {
	idx := strings.Index(name, "-")
	if idx <= 0 {
		return ""
	}
	return strings.ToLower(name[:idx])
}

// ZoneFor resolves name's venue-abbreviation prefix against the lookup,
// returning "" if there's no candidate or no match.
func (va VenueAbbrLookup) ZoneFor(name string) string {
	if va == nil {
		return ""
	}
	abbr := AbbreviationCandidate(name)
	if abbr == "" {
		return ""
	}
	return va[abbr]
}

// NormalizeMAC replaces ':' with '-', trims leading/trailing '-'. No case
// conversion - the original casing is preserved so the same physical device
// produces the same instance identifier across agents.
func NormalizeMAC(mac string) string {
	mac = strings.TrimSpace(mac)
	if mac == "" {
		return ""
	}
	converted := strings.TrimSpace(strings.Trim(strings.ReplaceAll(mac, ":", "-"), "-"))
	if converted == "" || !containsAlnum(converted) {
		return ""
	}
	return converted
}

// NormalizeSerial trims whitespace and requires at least one alphanumeric
// character. No case conversion.
func NormalizeSerial(serial string) string {
	serial = strings.TrimSpace(serial)
	if serial == "" || !containsAlnum(serial) {
		return ""
	}
	return serial
}

// CleanOwnName cleans the device's own reported name for use as an instance
// name fallback: '_' and ':' both become '-' (the baicells-agent convention -
// unlike the mimosa/tarana agents' CleanDeviceName, which maps '_' to '.').
func CleanOwnName(name string) string {
	name = strings.TrimSpace(name)
	if name == "" {
		return ""
	}
	cleaned := strings.ReplaceAll(name, "_", "-")
	cleaned = strings.ReplaceAll(cleaned, ":", "-")
	return strings.Trim(strings.TrimSpace(cleaned), "-")
}

// BuildInstanceName returns the instance name and true, or "", false if the
// device has no usable identity (Inventory MAC/serial/object key all missing
// and the device's own name is also empty) - the caller must drop the
// device rather than sending it under any other fallback identifier.
func BuildInstanceName(devInfo DeviceInfo, ownName string) (string, bool) {
	invMAC := NormalizeMAC(devInfo.MACAddress)
	invSerial := NormalizeSerial(devInfo.SerialNumber)

	switch {
	case invMAC != "":
		return "MAC " + invMAC, true
	case invSerial != "":
		return "SERIAL " + invSerial, true
	case devInfo.ObjectKey != "":
		return "JIRAKEY " + devInfo.ObjectKey, true
	case ownName != "":
		return ownName, true
	default:
		return "", false
	}
}

func containsAlnum(s string) bool {
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return true
		}
	}
	return false
}

// Refresh queries the Device Inventory API for every device (MAC -> serial ->
// name, first match wins) and returns the new Lookup containing only the
// devices actually found. It does not write to disk - callers merge the
// result into their in-memory cache and call Save() afterward. Returns nil
// if the API is unreachable/misconfigured, so the caller can keep the
// existing cache.
func Refresh(cfg config.DeviceInventoryConfig, items []Identifiers) Lookup {
	if cfg.APIKey == "" || cfg.BaseURL == "" {
		logrus.Warn("DeviceLookup: device_inventory api_key/base_url not configured, skipping refresh")
		return nil
	}
	timeout := time.Duration(cfg.TimeoutSec) * time.Second
	client := &http.Client{Timeout: timeout}

	if !isHealthy(client, cfg.BaseURL) {
		logrus.Warn("DeviceLookup: inventory API unreachable, keeping existing lookup")
		return nil
	}

	// Dedup by whichever identifier is available.
	uniq := make(map[string]Identifiers)
	for _, it := range items {
		key := firstNonEmpty(it.MAC, it.Serial, it.Name)
		if key == "" {
			continue
		}
		uniq[key] = it
	}
	if len(uniq) == 0 {
		logrus.Info("DeviceLookup: no devices to refresh")
		return make(Lookup)
	}

	logrus.Infof("DeviceLookup: refreshing %d devices (concurrency=%d)...", len(uniq), lookupConcurrency)
	startTime := time.Now()

	type result struct {
		key   string
		entry Entry
		ok    bool
	}

	sem := make(chan struct{}, lookupConcurrency)
	resultCh := make(chan result, len(uniq))
	var wg sync.WaitGroup
	var completed int64
	total := len(uniq)

	for key, it := range uniq {
		wg.Add(1)
		sem <- struct{}{}
		go func(key string, it Identifiers) {
			defer wg.Done()
			defer func() { <-sem }()
			defer func() { atomic.AddInt64(&completed, 1) }()

			var identifier string
			var raw map[string]interface{}
			for _, candidate := range [...]string{it.RawMAC, it.Serial, it.Name} {
				if candidate == "" {
					continue
				}
				identifier = candidate
				raw = lookupByIdentifier(client, cfg.APIKey, cfg.BaseURL, cfg.MaxRetry, time.Duration(cfg.RetryDelayMs)*time.Millisecond, candidate)
				if raw != nil {
					break
				}
			}
			if raw == nil {
				resultCh <- result{ok: false}
				return
			}
			resultCh <- result{
				key: key,
				entry: Entry{
					IdentifierUsed: identifier,
					Device:         extractDeviceInfo(raw),
				},
				ok: true,
			}
		}(key, it)
	}

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(resultCh)
		close(done)
	}()

	// Log progress periodically since a full refresh of thousands of devices
	// can take many minutes and would otherwise look hung.
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				n := atomic.LoadInt64(&completed)
				logrus.Infof("DeviceLookup: progress %d/%d (%.0f%%), elapsed=%v",
					n, total, 100*float64(n)/float64(total), time.Since(startTime).Round(time.Second))
			}
		}
	}()

	newLookup := make(Lookup, len(uniq))
	found, failed := 0, 0
	for r := range resultCh {
		if r.ok {
			newLookup[r.key] = r.entry
			found++
		} else {
			failed++
		}
	}

	logrus.Infof("DeviceLookup: done - %d found, %d not found, elapsed=%v",
		found, failed, time.Since(startTime).Round(time.Second))

	if found == 0 && len(uniq) > 0 {
		// Legitimate for an incremental refresh of already-known-not-found
		// devices - they're still not in the inventory. Still return the
		// (empty) result rather than nil so the caller can record these as
		// not-found and stop re-querying them every cycle; nil is reserved
		// for "the API itself is unreachable/misconfigured" (see above).
		logrus.Warn("DeviceLookup: refresh found 0 devices among the queried set")
	}

	return newLookup
}

// Save persists the (possibly merged) cache to disk. Callers that invoke
// Refresh() incrementally should merge the result into their in-memory cache
// and call this afterward, rather than relying on Refresh() to write the
// whole file itself.
func Save(dl Lookup) {
	atomicWriteJSON(lookupPath, dl)
}

func isHealthy(client *http.Client, baseURL string) bool {
	resp, err := client.Get(baseURL + "/health")
	if err != nil {
		logrus.Warnf("DeviceLookup: health check failed: %v", err)
		return false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		logrus.Warnf("DeviceLookup: health check returned HTTP %d", resp.StatusCode)
		return false
	}
	return true
}

func lookupByIdentifier(client *http.Client, apiKey, baseURL string, maxRetry int, retryDelay time.Duration, identifier string) map[string]interface{} {
	if identifier == "" {
		return nil
	}
	url := fmt.Sprintf("%s/devices/%s", baseURL, neturl.PathEscape(identifier))

	for attempt := 1; attempt <= maxRetry; attempt++ {
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			return nil
		}
		req.Header.Set("X-API-Key", apiKey)
		req.Header.Set("Accept", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			if attempt < maxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			if attempt < maxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}

		if resp.StatusCode == http.StatusNotFound {
			return nil
		}
		if resp.StatusCode != http.StatusOK {
			if attempt < maxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}

		bodyStr := strings.TrimSpace(string(body))
		if bodyStr == "" || bodyStr == "null" {
			return nil
		}
		var result map[string]interface{}
		if err := json.Unmarshal([]byte(bodyStr), &result); err != nil {
			return nil
		}
		return result
	}
	return nil
}

// extractDeviceInfo parses the raw API response into DeviceInfo. Component
// name is only set when both manufacturer and device_class are present in
// the inventory record - no "NONE-NONE" style placeholder, matching the
// baicells-agent convention of no default value at all.
func extractDeviceInfo(raw map[string]interface{}) DeviceInfo {
	dev, _ := raw["device"].(map[string]interface{})
	if dev == nil {
		dev = raw
	}
	meta, _ := dev["meta"].(map[string]interface{})
	model, _ := dev["model"].(map[string]interface{})

	manufacturer := stringVal(model, "manufacturer")
	if manufacturer == "" {
		manufacturer = stringVal(meta, "manufacturer")
	}
	deviceClass := stringVal(model, "device_class")

	var componentName string
	if manufacturer != "" && deviceClass != "" {
		componentName = manufacturer + "-" + deviceClass
	}

	return DeviceInfo{
		SerialNumber:  stringVal(dev, "serial_number"),
		ObjectKey:     stringVal(dev, "object_key"),
		MACAddress:    stringVal(dev, "mac_address"),
		Name:          stringVal(dev, "name"),
		Venue:         stringVal(meta, "venue"),
		ComponentName: componentName,
		IPAddress:     stringVal(dev, "ip_address"),
	}
}

// stringVal reads a string field, treating the inventory's own "unknown
// value" placeholders ("-", "n/a", etc.) the same as a missing field so
// callers can fall back to the device's own reported identity instead.
func stringVal(m map[string]interface{}, key string) string {
	if m == nil {
		return ""
	}
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	s, _ := v.(string)
	if isPlaceholder(s) {
		return ""
	}
	return s
}

// isPlaceholder recognizes the inventory's various "no data" conventions:
// known placeholder words, plus - generically - any value with no letter or
// digit at all (".", "-", "--", "...", "?", etc.), since a real MAC/IP/serial
// always contains at least one alphanumeric character.
func isPlaceholder(s string) bool {
	trimmed := strings.TrimSpace(s)
	switch strings.ToLower(trimmed) {
	case "", "n/a", "na", "none", "null", "unknown", "tbd":
		return true
	}
	return !containsAlnum(trimmed)
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if v != "" {
			return v
		}
	}
	return ""
}

func atomicWriteJSON(path string, data interface{}) {
	b, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		logrus.Warnf("DeviceLookup: failed to marshal for disk: %v", err)
		return
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0644); err != nil {
		logrus.Warnf("DeviceLookup: failed to write tmp file: %v", err)
		return
	}
	if err := os.Rename(tmp, path); err != nil {
		logrus.Warnf("DeviceLookup: failed to rename tmp file: %v", err)
	}
}
