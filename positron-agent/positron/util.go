package positron

import (
	"regexp"
	"strings"
	"time"

	"github.com/insightfinder/positron-agent/devicelookup"
	"github.com/insightfinder/positron-agent/pkg/models"
)

var bareNumberRe = regexp.MustCompile(`^[0-9]+$`)

// looksLikeName reports whether s is usable as a device name: non-empty and
// not just a bare number (a port/slot index, not a hostname).
func looksLikeName(s string) bool {
	s = strings.TrimSpace(s)
	return s != "" && !bareNumberRe.MatchString(s)
}

// OwnName picks the endpoint's real name from the two competing fields
// Positron exposes. ConfEndpointName holds the assigned hostname for the
// large majority (~93%) of endpoints, so it's preferred whenever it looks
// like a real name; ConfUserName is only used as a fallback when
// ConfEndpointName is empty or has been reduced to a bare port/slot number
// (e.g. "10105", "155") - which is otherwise sent as the instance name
// verbatim. Neither field is reliably populated on its own: provisioning
// sometimes updates one and not the other, so this is a best-effort pick,
// not a guarantee of a real name.
func (e *Endpoint) OwnName() string {
	if looksLikeName(e.ConfEndpointName) {
		return e.ConfEndpointName
	}
	if looksLikeName(e.ConfUserName) {
		return e.ConfUserName
	}
	return e.ConfEndpointName
}

// resolveComponentName picks endpointName or gamName from config based on
// what this record actually is - a GAM headend unit also gets surfaced
// through /endpoint/list/all (not just /device/list), identified by
// ModelType "GAM-C" as opposed to a regular CPE's "G1001-C"/"G1001-CR".
// ModelType is empty/"Unknown" when the endpoint is offline and Positron
// couldn't detect its model; in that case fall back to checking the
// endpoint's own name for a "GAM" marker before defaulting to endpointName.
func (e *Endpoint) resolveComponentName(endpointName, gamName string) string {
	if e.ModelType == "GAM-C" {
		return gamName
	}
	own := strings.ToUpper(e.ConfEndpointName + " " + e.ConfUserName)
	if strings.Contains(own, "GAM") {
		return gamName
	}
	return endpointName
}

// ToMetricData converts an Endpoint to MetricData, enriching it from the
// Device Inventory lookup (MAC > serial > own name, first match wins).
// componentName is endpointName or gamName from config
// (positron.endpoint_component_name / positron.gam_component_name) - see
// resolveComponentName.
// Returns ok=false if the device has no usable instance name (Inventory
// miss and no own name) - the caller must drop it rather than send it under
// any other fallback identifier.
func (e *Endpoint) ToMetricData(dl devicelookup.Lookup, va devicelookup.VenueAbbrLookup, endpointName, gamName string) (*models.MetricData, bool) {
	ownMAC := devicelookup.NormalizeMAC(e.MacAddress)
	ownSerial := devicelookup.NormalizeSerial(e.SerialNumber)
	rawOwnName := e.OwnName()
	ownName := devicelookup.CleanOwnName(rawOwnName)

	devInfo := dl.GetDeviceInfo(ownMAC, ownSerial, ownName)

	// Zone: Inventory only > venue-abbreviation fallback - own name prefix
	// first, then (if that has no "<ABBR>-" prefix or it isn't a registered
	// abbreviation) the parent GAM's name, which reliably carries the
	// abbreviation even when the endpoint's own name doesn't. When the GAM
	// fallback is what resolves the zone, its abbreviation is prefixed onto
	// the device's own name too, e.g. "10075SE22ndPath-GN" ->
	// "SSVL-10075SE22ndPath-GN", so instance/display name carry it.
	zone := devInfo.Venue
	if zone == "" {
		var prefix string
		zone, prefix = va.ZoneForWithFallback(rawOwnName, e.Gam.Name)
		if prefix != "" {
			rawOwnName = prefix + "-" + rawOwnName
			ownName = devicelookup.CleanOwnName(rawOwnName)
		}
	}

	instanceName, ok := devicelookup.BuildInstanceName(devInfo, ownName)
	if !ok {
		return nil, false
	}

	// Use current Unix timestamp in seconds, will be converted to ms later
	currentTime := time.Now().Unix()

	metric := &models.MetricData{
		Timestamp: currentTime,
		// Display name: always the device's own raw name (as reported,
		// uncleaned) - never falls back to Inventory's name field.
		InstanceName:  instanceName,
		DisplayName:   rawOwnName,
		ComponentName: e.resolveComponentName(endpointName, gamName),
		Zone:          zone,
		IP:            devInfo.IPAddress, // Endpoints report no IP of their own
		Data: map[string]interface{}{
			// Format metric names using safe formatting
			models.MakeSafeDataKey("DS PHY rate"): e.RxPhyRate,
			models.MakeSafeDataKey("US PHY rate"): e.TxPhyRate,
			models.MakeSafeDataKey("DS Max BW"):   e.RxMaxXput,
			models.MakeSafeDataKey("US Max BW"):   e.TxMaxXput,
		},
	}

	return metric, true
}

// resolveComponentName picks gamName or endpointName from config. Every
// device seen on /device/list is a GAM headend unit in practice (confirmed
// by ProductClass, e.g. "GAM4CX"/"GAM4CXAC" - always populated), so gamName
// is the default; the ProductClass/name checks only guard against a future
// device that's genuinely not a GAM (ProductClass changes, or - like the
// name says - isn't one).
func (d *Device) resolveComponentName(gamName, endpointName string) string {
	if strings.Contains(strings.ToUpper(d.ProductClass), "GAM") {
		return gamName
	}
	if strings.Contains(strings.ToUpper(d.Name), "GN") {
		return endpointName
	}
	return gamName
}

// ToMetricData converts a Device to MetricData, enriching it from the Device
// Inventory lookup (serial > own name, first match wins - devices report no
// MAC of their own). componentName is gamName or endpointName from config
// (positron.gam_component_name / positron.endpoint_component_name) - see
// resolveComponentName. Returns ok=false if the device has no usable
// instance name (Inventory miss and no own name).
func (d *Device) ToMetricData(dl devicelookup.Lookup, va devicelookup.VenueAbbrLookup, gamName, endpointName string) (*models.MetricData, bool) {
	ownSerial := devicelookup.NormalizeSerial(d.SerialNumber)
	rawOwnName := d.Name
	ownName := devicelookup.CleanOwnName(rawOwnName)

	devInfo := dl.GetDeviceInfo(ownSerial, ownName)
	instanceName, ok := devicelookup.BuildInstanceName(devInfo, ownName)
	if !ok {
		return nil, false
	}

	// Zone: Inventory only > venue-abbreviation fallback (from the device's
	// own name prefix, for devices the Inventory lookup never matched at all).
	zone := devInfo.Venue
	if zone == "" {
		zone = va.ZoneFor(rawOwnName)
	}

	// IP: Inventory ip_address > the device's own reported IP (excluding the
	// "0.0.0.0" unset/unreachable placeholder).
	ip := devInfo.IPAddress
	if ip == "" && d.IPAddress != "0.0.0.0" {
		ip = d.IPAddress
	}

	// Use current Unix timestamp in seconds, will be converted to ms later
	currentTime := time.Now().Unix()

	metric := &models.MetricData{
		Timestamp:     currentTime,
		InstanceName:  instanceName,
		DisplayName:   rawOwnName,
		ComponentName: d.resolveComponentName(gamName, endpointName),
		Zone:          zone,
		IP:            ip,
		Data: map[string]interface{}{
			// Format metric names using safe formatting - Capacity Metrics
			models.MakeSafeDataKey("Ports"):       d.Ports,
			models.MakeSafeDataKey("Endpoints"):   d.Endpoints,
			models.MakeSafeDataKey("Subscribers"): d.Subscribers,
			models.MakeSafeDataKey("Bandwidths"):  d.Bandwidths,
		},
	}

	return metric, true
}

// Convert Alarm to LogData
func (a *Alarm) ToLogData() map[string]interface{} {
	// Use current Unix timestamp in milliseconds for logs
	currentTimeMs := time.Now().Unix() * 1000

	// Build a comprehensive data object to include all alarm details under "data"
	data := map[string]interface{}{
		// A human-readable message
		"message": a.Description + ": " + a.Condition,
		// Core alarm fields
		"system_name":          a.SystemName,
		"product_class":        a.ProductClass,
		"severity":             a.Severity,
		"condition":            a.Condition,
		"service_affecting":    a.ServiceAffecting,
		"description":          a.Description,
		"occurred":             a.Occurred,
		"device_serial_number": a.DeviceSerialNumber,
		"received":             a.Received,
		"cleared":              a.Cleared,
		"details":              a.Details,
	}

	return map[string]interface{}{
		"timestamp": currentTimeMs,
		"tag":       models.CleanDeviceName(a.SystemName),
		// "componentName": models.CleanDeviceName(a.SystemName),
		"data": data,
	}
}

// // Utility functions
// func boolToInt(b bool) int {
// 	if b {
// 		return 1
// 	}
// 	return 0
// }

// // parseUptime tries to parse uptime string to seconds
// // Supports formats like "11 days, 15h 43m 24s" or "0 days, 0h 14m 48s" or "12d 09:09:08"
// func parseUptime(uptime string) int64 {
// 	// Try format: "11 days, 15h 43m 24s"
// 	re1 := regexp.MustCompile(`(\d+)\s+days?,\s*(\d+)h\s*(\d+)m\s*(\d+)s`)
// 	if matches := re1.FindStringSubmatch(uptime); len(matches) == 5 {
// 		days, _ := strconv.Atoi(matches[1])
// 		hours, _ := strconv.Atoi(matches[2])
// 		minutes, _ := strconv.Atoi(matches[3])
// 		seconds, _ := strconv.Atoi(matches[4])

// 		return int64(days*24*3600 + hours*3600 + minutes*60 + seconds)
// 	}

// 	// Try format: "12d 09:09:08"
// 	re2 := regexp.MustCompile(`(\d+)d\s+(\d+):(\d+):(\d+)`)
// 	if matches := re2.FindStringSubmatch(uptime); len(matches) == 5 {
// 		days, _ := strconv.Atoi(matches[1])
// 		hours, _ := strconv.Atoi(matches[2])
// 		minutes, _ := strconv.Atoi(matches[3])
// 		seconds, _ := strconv.Atoi(matches[4])

// 		return int64(days*24*3600 + hours*3600 + minutes*60 + seconds)
// 	}

// 	return 0 // Could not parse
// }
