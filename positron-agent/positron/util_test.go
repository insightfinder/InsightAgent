package positron

import (
	"testing"

	"github.com/insightfinder/positron-agent/devicelookup"
)

func TestEndpointToMetricData_ZoneAbbreviationFallsBackToGamName(t *testing.T) {
	e := &Endpoint{
		ConfEndpointName: "10075SE22ndPath-GN",
		ConfUserName:     "SSVL-10075SE22ndPath-GN",
	}
	e.Gam.Name = "SSVL-2236SE100thLane-GAM"

	va := devicelookup.VenueAbbrLookup{"ssvl": "Sunset Valley"}
	dl := devicelookup.Lookup{}

	metric, ok := e.ToMetricData(dl, va, "Endpoint", "GAM")
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.Zone != "Sunset Valley" {
		t.Errorf("Zone = %q, want %q", metric.Zone, "Sunset Valley")
	}
	if metric.InstanceName != "SSVL-10075SE22ndPath-GN" {
		t.Errorf("InstanceName = %q, want %q", metric.InstanceName, "SSVL-10075SE22ndPath-GN")
	}
	if metric.DisplayName != "SSVL-10075SE22ndPath-GN" {
		t.Errorf("DisplayName = %q, want %q", metric.DisplayName, "SSVL-10075SE22ndPath-GN")
	}
}

func TestEndpointToMetricData_OwnNameAbbreviationTakesPriority(t *testing.T) {
	e := &Endpoint{
		ConfEndpointName: "MEAD-Cabin1-GN",
	}
	e.Gam.Name = "SSVL-2236SE100thLane-GAM"

	va := devicelookup.VenueAbbrLookup{
		"mead": "Meadowbrook",
		"ssvl": "Sunset Valley",
	}
	dl := devicelookup.Lookup{}

	metric, ok := e.ToMetricData(dl, va, "Endpoint", "GAM")
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.Zone != "Meadowbrook" {
		t.Errorf("Zone = %q, want %q", metric.Zone, "Meadowbrook")
	}
	if metric.InstanceName != "MEAD-Cabin1-GN" {
		t.Errorf("InstanceName = %q, want %q (should not be re-prefixed)", metric.InstanceName, "MEAD-Cabin1-GN")
	}
}

func TestEndpointToMetricData_InventoryVenueTakesPriorityOverFallback(t *testing.T) {
	e := &Endpoint{
		ConfEndpointName: "10075SE22ndPath-GN",
	}
	e.Gam.Name = "SSVL-2236SE100thLane-GAM"

	va := devicelookup.VenueAbbrLookup{"ssvl": "Sunset Valley"}
	dl := devicelookup.Lookup{
		"10075SE22ndPath-GN": {
			Device: devicelookup.DeviceInfo{Venue: "Inventory Venue"},
		},
	}

	metric, ok := e.ToMetricData(dl, va, "Endpoint", "GAM")
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.Zone != "Inventory Venue" {
		t.Errorf("Zone = %q, want %q", metric.Zone, "Inventory Venue")
	}
	if metric.InstanceName != "10075SE22ndPath-GN" {
		t.Errorf("InstanceName = %q, want %q (no prefix expected)", metric.InstanceName, "10075SE22ndPath-GN")
	}
}
