// Package devicelookup enriches devices with data from the Device Inventory /
// Asset Registry API, keyed by MAC address, serial number, or device name
// (first match wins). This mirrors the lookup used by the mimosa and
// netexperience agents so the same physical device resolves to the same
// InsightFinder instance identity across agents.
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
	"time"
	"unicode"

	"github.com/sirupsen/logrus"
	"github.com/tarana/gnmic-agent/config"
)

const lookupPath = "devicelookup.json"
const lookupConcurrency = 20

// DeviceInfo holds the fields we need from the device inventory API response.
type DeviceInfo struct {
	SerialNumber  string `json:"serial_number"`
	ObjectKey     string `json:"object_key"`
	MACAddress    string `json:"mac_address"`
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
	MAC    string
	Serial string
	Name   string
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

// NormalizeMAC mirrors the mimosa/netexperience agents' MAC normalization:
// replace ':' with '-', trim leading/trailing '-', require an alphanumeric char.
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

// NormalizeSerial mirrors the mimosa/netexperience agents' serial normalization.
func NormalizeSerial(serial string) string {
	serial = strings.TrimSpace(serial)
	if serial == "" || !containsAlnum(serial) {
		return ""
	}
	return serial
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
// name, first match wins) and returns the new Lookup. Also persists it to disk.
// If the API is unreachable, it returns nil so the caller can keep the existing cache.
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

	for key, it := range uniq {
		wg.Add(1)
		sem <- struct{}{}
		go func(key string, it Identifiers) {
			defer wg.Done()
			defer func() { <-sem }()

			var identifier string
			var raw map[string]interface{}
			for _, candidate := range [...]string{it.MAC, it.Serial, it.Name} {
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

	go func() {
		wg.Wait()
		close(resultCh)
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

	logrus.Infof("DeviceLookup: done — %d found, %d not found, elapsed=%v",
		found, failed, time.Since(startTime).Round(time.Second))

	if found == 0 && len(uniq) > 0 {
		logrus.Warn("DeviceLookup: refresh found 0 devices, keeping previous cache")
		return nil
	}

	atomicWriteJSON(lookupPath, newLookup)
	return newLookup
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

// extractDeviceInfo parses the raw API response into DeviceInfo.
// API shape: { "device": {...} } or the device object directly.
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
	if manufacturer == "" {
		manufacturer = "NONE"
	}
	deviceClass := stringVal(model, "device_class")
	if deviceClass == "" {
		deviceClass = "NONE"
	}

	return DeviceInfo{
		SerialNumber:  stringVal(dev, "serial_number"),
		ObjectKey:     stringVal(dev, "object_key"),
		MACAddress:    stringVal(dev, "mac_address"),
		Venue:         stringVal(meta, "venue"),
		ComponentName: manufacturer + "-" + deviceClass,
		IPAddress:     stringVal(dev, "ip_address"),
	}
}

func stringVal(m map[string]interface{}, key string) string {
	if m == nil {
		return ""
	}
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	s, _ := v.(string)
	return s
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
