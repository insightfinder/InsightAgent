package ruckus

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

const (
	deviceLookupPath  = "devicelookup.json"
	lookupConcurrency = 20
	lookupRetryDelay  = 500 * time.Millisecond
)

// DeviceInfo holds fields from the device inventory API
type DeviceInfo struct {
	MACAddress    string `json:"mac_address"`
	SerialNumber  string `json:"serial_number"`
	ObjectKey     string `json:"object_key"`
	Name          string `json:"name"`
	Venue         string `json:"venue"`          // device.meta.venue -> used as zone
	ComponentName string `json:"component_name"` // manufacturer-device_class
	IPAddress     string `json:"ip_address"`     // device.ip_address
}

// DeviceLookupEntry caches one device lookup result
type DeviceLookupEntry struct {
	IdentifierUsed string     `json:"identifier_used"`
	Device         DeviceInfo `json:"device"`
}

// DeviceLookup maps AP MAC (lowercase) -> DeviceLookupEntry
type DeviceLookup map[string]DeviceLookupEntry

// APIdentifier carries the identifiers used to query the inventory API,
// tried in priority order: MAC -> Serial -> IP -> Name.
type APIdentifier struct {
	MAC    string
	Serial string
	IP     string
	Name   string
}

// LoadDeviceLookup loads devicelookup.json from disk; returns empty map if not found
func LoadDeviceLookup() DeviceLookup {
	data, err := os.ReadFile(deviceLookupPath)
	if err != nil {
		if !os.IsNotExist(err) {
			logrus.Warnf("DeviceLookup: failed to read %s: %v", deviceLookupPath, err)
		}
		return make(DeviceLookup)
	}
	var dl DeviceLookup
	if err := json.Unmarshal(data, &dl); err != nil {
		logrus.Warnf("DeviceLookup: failed to parse %s, starting fresh: %v", deviceLookupPath, err)
		return make(DeviceLookup)
	}
	logrus.Infof("DeviceLookup: loaded %d entries from disk", len(dl))
	return dl
}

// DeviceLookupIsStale returns true if devicelookup.json is missing or older than 24h
func DeviceLookupIsStale() bool {
	info, err := os.Stat(deviceLookupPath)
	if err != nil {
		return true
	}
	return time.Since(info.ModTime()) >= 24*time.Hour
}

// Lookup returns the cached DeviceInfo for a given AP MAC and whether the device
// was found in the inventory. A device that is not found must be discarded (not
// reported to InsightFinder), so callers rely on the bool rather than the zero value.
// DeviceLookup maps are immutable once stored — no lock needed here.
func (dl DeviceLookup) Lookup(mac string) (DeviceInfo, bool) {
	if dl == nil || mac == "" {
		return DeviceInfo{}, false
	}
	entry, ok := dl[strings.ToLower(mac)]
	if !ok {
		return DeviceInfo{}, false
	}
	return entry.Device, true
}

// inventoryAPIIsHealthy does a quick health check before a bulk refresh
func inventoryAPIIsHealthy(baseURL string, timeout time.Duration) bool {
	client := &http.Client{Timeout: timeout}
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

// RefreshDeviceLookup queries the device inventory API for all APs (MAC first,
// fallback serial, fallback IP address) and returns the new DeviceLookup map. If the API is unreachable
// or the refresh finds nothing, the previous lookup is returned unchanged so a good
// cache is never wiped by an outage. The caller stores the result under its own lock.
func (s *Service) RefreshDeviceLookup(identifiers []APIdentifier, previous DeviceLookup) DeviceLookup {
	apiKey := s.Config.DeviceInventoryAPIKey
	baseURL := s.Config.DeviceInventoryBaseURL
	if apiKey == "" || baseURL == "" {
		logrus.Warn("DeviceLookup: device_inventory_api_key/base_url not configured, skipping refresh")
		return previous
	}
	timeout := time.Duration(s.Config.DeviceInventoryTimeoutSec) * time.Second
	maxRetry := s.Config.DeviceInventoryMaxRetry

	if !inventoryAPIIsHealthy(baseURL, timeout) {
		logrus.Warnf("DeviceLookup: inventory API unreachable, keeping existing lookup (%d entries); "+
			"unmatched devices will use fallback values", len(previous))
		return previous
	}

	if len(identifiers) == 0 {
		logrus.Info("DeviceLookup: no AP identifiers provided, skipping refresh")
		return previous
	}

	logrus.Infof("DeviceLookup: refreshing %d devices (concurrency=%d)...", len(identifiers), lookupConcurrency)
	startTime := time.Now()
	client := &http.Client{Timeout: timeout}

	type result struct {
		key   string
		entry DeviceLookupEntry
		ok    bool
	}

	sem := make(chan struct{}, lookupConcurrency)
	resultCh := make(chan result, len(identifiers))
	var wg sync.WaitGroup

	for _, item := range identifiers {
		if item.MAC == "" && item.Serial == "" && item.IP == "" && item.Name == "" {
			continue
		}
		wg.Add(1)
		sem <- struct{}{}
		go func(it APIdentifier) {
			defer wg.Done()
			defer func() { <-sem }()

			// Query priority: MAC -> Serial -> IP -> Name.
			identifier := strings.ToLower(it.MAC)
			raw := lookupDeviceByIdentifier(client, apiKey, baseURL, maxRetry, identifier)
			if raw == nil && it.Serial != "" {
				identifier = it.Serial
				raw = lookupDeviceByIdentifier(client, apiKey, baseURL, maxRetry, identifier)
			}
			if raw == nil && it.IP != "" {
				identifier = it.IP
				raw = lookupDeviceByIdentifier(client, apiKey, baseURL, maxRetry, identifier)
			}
			if raw == nil && it.Name != "" {
				identifier = it.Name
				raw = lookupDeviceByIdentifier(client, apiKey, baseURL, maxRetry, identifier)
			}

			if raw == nil {
				resultCh <- result{ok: false}
				return
			}

			key := strings.ToLower(it.MAC)
			switch {
			case key != "":
			case it.Serial != "":
				key = it.Serial
			case it.IP != "":
				key = it.IP
			default:
				key = it.Name
			}
			if key == "" {
				key = it.IP
			}
			resultCh <- result{
				key: key,
				entry: DeviceLookupEntry{
					IdentifierUsed: identifier,
					Device:         extractDeviceInfo(raw),
				},
				ok: true,
			}
		}(item)
	}

	go func() {
		wg.Wait()
		close(resultCh)
	}()

	newDL := make(DeviceLookup, len(identifiers))
	success, failed := 0, 0
	for r := range resultCh {
		if r.ok {
			newDL[r.key] = r.entry
			success++
		} else {
			failed++
		}
	}

	logrus.Infof("DeviceLookup: done - %d found, %d not found, elapsed=%v",
		success, failed, time.Since(startTime).Round(time.Second))

	// safety: if nothing was found but we had a non-empty cache, the API likely
	// failed mid-run — keep the old cache instead of wiping it
	if success == 0 && len(previous) > 0 {
		logrus.Warnf("DeviceLookup: refresh found 0 devices, keeping previous %d entries", len(previous))
		return previous
	}

	atomicWriteJSON(deviceLookupPath, newDL)
	return newDL
}

// lookupDeviceByIdentifier calls GET /devices/{identifier} with retry.
// Returns nil if the device is not found or any permanent error occurs.
func lookupDeviceByIdentifier(client *http.Client, apiKey, baseURL string, maxRetry int, identifier string) map[string]interface{} {
	if identifier == "" {
		return nil
	}
	url := fmt.Sprintf("%s/devices/%s", baseURL, identifier)

	var lastErr error
	for attempt := 1; attempt <= maxRetry; attempt++ {
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			return nil
		}
		req.Header.Set("X-API-Key", apiKey)
		req.Header.Set("Accept", "application/json")
		resp, err := client.Do(req)
		if err != nil {
			lastErr = err
			if attempt < maxRetry {
				time.Sleep(lookupRetryDelay)
			}
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			lastErr = err
			if attempt < maxRetry {
				time.Sleep(lookupRetryDelay)
			}
			continue
		}

		if resp.StatusCode == http.StatusNotFound {
			return nil
		}
		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
			if attempt < maxRetry {
				time.Sleep(lookupRetryDelay)
			}
			continue
		}

		bodyStr := strings.TrimSpace(string(body))
		if bodyStr == "" || bodyStr == "null" {
			return nil
		}

		var result map[string]interface{}
		if err := json.Unmarshal([]byte(bodyStr), &result); err != nil {
			lastErr = err
			break // malformed JSON — no point retrying
		}
		return result
	}

	if lastErr != nil {
		logrus.Debugf("DeviceLookup: lookup failed for %s: %v", identifier, lastErr)
	}
	return nil
}

// atomicWriteJSON marshals data to JSON and writes to path via a .tmp file
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

// extractDeviceInfo parses the device inventory API response into DeviceInfo
func extractDeviceInfo(raw map[string]interface{}) DeviceInfo {
	dev, _ := raw["device"].(map[string]interface{})
	if dev == nil {
		dev = raw // the API returns the device object directly
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
		MACAddress:    stringVal(dev, "mac_address"),
		SerialNumber:  stringVal(dev, "serial_number"),
		ObjectKey:     stringVal(dev, "object_key"),
		Name:          stringVal(dev, "name"),
		Venue:         stringVal(meta, "venue"),
		ComponentName: manufacturer + "-" + deviceClass,
		IPAddress:     stringVal(dev, "ip_address"),
	}
}

// stringVal safely extracts a string value from a map
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
