package positron

import (
	"testing"

	"github.com/insightfinder/positron-agent/devicelookup"
)

func TestEndpointToMetricData_ComponentNameIsFixed(t *testing.T) {
	e := &Endpoint{
		ConfEndpointName: "10075SE22ndPath-GN",
	}
	dl := devicelookup.Lookup{}

	metric, ok := e.ToMetricData(dl)
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.ComponentName != "Positron Agent" {
		t.Errorf("ComponentName = %q, want %q", metric.ComponentName, "Positron Agent")
	}
}

func TestEndpointToMetricData_ZoneLeftEmptyEvenWithInventoryVenue(t *testing.T) {
	e := &Endpoint{
		ConfEndpointName: "10075SE22ndPath-GN",
	}
	dl := devicelookup.Lookup{
		"10075SE22ndPath-GN": {
			Device: devicelookup.DeviceInfo{Venue: "Inventory Venue"},
		},
	}

	metric, ok := e.ToMetricData(dl)
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.Zone != "" {
		t.Errorf("Zone = %q, want empty (zone is temporarily disabled)", metric.Zone)
	}
	if metric.InstanceName != "10075SE22ndPath-GN" {
		t.Errorf("InstanceName = %q, want %q", metric.InstanceName, "10075SE22ndPath-GN")
	}
}

func TestDeviceToMetricData_ComponentNameIsFixed(t *testing.T) {
	d := &Device{Name: "SSVL-2236SE100thLane-GAM"}
	dl := devicelookup.Lookup{}

	metric, ok := d.ToMetricData(dl)
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.ComponentName != "Positron Agent" {
		t.Errorf("ComponentName = %q, want %q", metric.ComponentName, "Positron Agent")
	}
}

func TestDeviceToMetricData_ZoneLeftEmptyEvenWithInventoryVenue(t *testing.T) {
	d := &Device{Name: "SSVL-2236SE100thLane-GAM"}
	dl := devicelookup.Lookup{
		"SSVL-2236SE100thLane-GAM": {
			Device: devicelookup.DeviceInfo{Venue: "Inventory Venue"},
		},
	}

	metric, ok := d.ToMetricData(dl)
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.Zone != "" {
		t.Errorf("Zone = %q, want empty (zone is temporarily disabled)", metric.Zone)
	}
}
