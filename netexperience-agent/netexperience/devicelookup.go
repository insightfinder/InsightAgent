package netexperience

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

const deviceLookupPath = "devicelookup.json"

// DeviceInfo holds fields from the device inventory API
type DeviceInfo struct {
	SerialNumber  string `json:"serial_number"`
	ObjectKey     string `json:"object_key"`
	MACAddress    string `json:"mac_address"`
	Venue         string `json:"venue"`          // device.meta.venue → used as zone
	ComponentName string `json:"component_name"` // manufacturer-device_class
	IPAddress     string `json:"ip_address"`     // device.ip_address
}

// DeviceLookupEntry caches one device lookup result
type DeviceLookupEntry struct {
	IdentifierUsed string     `json:"identifier_used"`
	Device         DeviceInfo `json:"device"`
}

// DeviceLookup is a thread-safe map from MAC → DeviceLookupEntry
type DeviceLookup map[string]DeviceLookupEntry

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

// GetDeviceInfo returns cached DeviceInfo for a given MAC address; zero value if not found.
// DeviceLookup maps are immutable once stored — no lock needed here.
func (dl DeviceLookup) GetDeviceInfo(mac string) DeviceInfo {
	if dl == nil {
		return DeviceInfo{}
	}
	entry, ok := dl[mac]
	if !ok {
		return DeviceInfo{}
	}
	return entry.Device
}

const lookupConcurrency = 20

// RefreshDeviceLookup queries the device inventory API for all cached equipment
// (MAC first, fallback serial) and returns the new DeviceLookup map.
// The caller is responsible for storing it safely (e.g. under a mutex).
func (s *Service) RefreshDeviceLookup() DeviceLookup {
	apiKey := s.config.DeviceInventoryAPIKey
	baseURL := s.config.DeviceInventoryBaseURL
	timeout := time.Duration(s.config.DeviceInventoryTimeoutSec) * time.Second
	maxRetry := s.config.DeviceInventoryMaxRetry
	retryDelay := time.Duration(s.config.DeviceInventoryRetryDelayMs) * time.Millisecond
	client := &http.Client{Timeout: timeout}

	s.cacheMutex.RLock()
	type equip struct{ mac, serial string }
	var items []equip
	for _, equipList := range s.cache.EquipmentByCustomer {
		for _, eq := range equipList {
			items = append(items, equip{
				mac:    eq.BaseMacAddress.AddressAsString,
				serial: eq.Serial,
			})
		}
	}
	s.cacheMutex.RUnlock()

	if len(items) == 0 {
		logrus.Info("DeviceLookup: no equipment in cache, skipping refresh")
		return make(DeviceLookup)
	}

	logrus.Infof("DeviceLookup: refreshing %d devices (concurrency=%d)...", len(items), lookupConcurrency)
	startTime := time.Now()

	type result struct {
		key   string
		entry DeviceLookupEntry
		ok    bool
	}

	sem := make(chan struct{}, lookupConcurrency)
	resultCh := make(chan result, len(items))
	var wg sync.WaitGroup

	for _, item := range items {
		if item.mac == "" && item.serial == "" {
			continue
		}
		wg.Add(1)
		sem <- struct{}{}
		go func(it equip) {
			defer wg.Done()
			defer func() { <-sem }()

			identifier := it.mac
			raw := lookupDeviceByIdentifier(client, apiKey, baseURL, maxRetry, retryDelay, identifier)
			if raw == nil && it.serial != "" {
				identifier = it.serial
				raw = lookupDeviceByIdentifier(client, apiKey, baseURL, maxRetry, retryDelay, identifier)
			}

			if raw == nil {
				resultCh <- result{ok: false}
				return
			}

			key := it.mac
			if key == "" {
				key = it.serial
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

	// Close resultCh after all goroutines finish
	go func() {
		wg.Wait()
		close(resultCh)
	}()

	// Collect results with progress logging
	newDL := make(DeviceLookup, len(items))
	success, failed, total := 0, 0, 0
	progressInterval := len(items) / 5
	if progressInterval < 50 {
		progressInterval = 50
	}
	for r := range resultCh {
		total++
		if r.ok {
			newDL[r.key] = r.entry
			success++
		} else {
			failed++
		}
		if total%progressInterval == 0 {
			logrus.Infof("DeviceLookup: progress %d/%d (found=%d, notfound=%d) elapsed=%v",
				total, len(items), success, failed, time.Since(startTime).Round(time.Second))
		}
	}

	logrus.Infof("DeviceLookup: done — %d found, %d not found, elapsed=%v",
		success, failed, time.Since(startTime).Round(time.Second))

	atomicWriteJSON(deviceLookupPath, newDL)
	return newDL
}

// lookupDeviceByIdentifier calls GET /devices/{identifier} with retry/timeout.
// Returns nil if the device is not found or any permanent error occurs.
func lookupDeviceByIdentifier(client *http.Client, apiKey, baseURL string, maxRetry int, retryDelay time.Duration, identifier string) map[string]interface{} {
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
				time.Sleep(retryDelay)
			}
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			lastErr = err
			if attempt < maxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}

		if resp.StatusCode == http.StatusNotFound {
			return nil
		}
		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("HTTP %d", resp.StatusCode)
			if attempt < maxRetry {
				time.Sleep(retryDelay)
			}
			continue
		}

		// Strip BOM / whitespace
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

// extractDeviceInfo parses the raw API response into DeviceInfo.
// API shape: { "device": { "mac_address", "serial_number", "object_key", "ip_address",
//   "meta": { "venue", "manufacturer" }, "model": { "manufacturer", "device_class" } } }
func extractDeviceInfo(raw map[string]interface{}) DeviceInfo {
	dev, _ := raw["device"].(map[string]interface{})
	if dev == nil {
		dev = raw // some endpoints return the device object directly
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
