package positron

import (
	"testing"

	"github.com/insightfinder/positron-agent/devicelookup"
)

func TestEndpointToMetricData_ComponentNameFixedAndZoneEmpty(t *testing.T) {
	e := &Endpoint{
		ConfEndpointName: "10075SE22ndPath-GN",
	}
	e.Gam.Name = "SSVL-2236SE100thLane-GAM"

	dl := devicelookup.Lookup{}

	metric, ok := e.ToMetricData(dl)
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.ComponentName != PositronAgentComponentName {
		t.Errorf("ComponentName = %q, want %q", metric.ComponentName, PositronAgentComponentName)
	}
	if metric.Zone != "" {
		t.Errorf("Zone = %q, want empty", metric.Zone)
	}
	if metric.InstanceName != "10075SE22ndPath-GN" {
		t.Errorf("InstanceName = %q, want %q", metric.InstanceName, "10075SE22ndPath-GN")
	}
	if metric.DisplayName != "10075SE22ndPath-GN" {
		t.Errorf("DisplayName = %q, want %q", metric.DisplayName, "10075SE22ndPath-GN")
	}
}

func TestDeviceToMetricData_ComponentNameFixedAndZoneEmpty(t *testing.T) {
	d := &Device{
		Name: "SSVL-2236SE100thLane-GAM",
	}

	dl := devicelookup.Lookup{}

	metric, ok := d.ToMetricData(dl)
	if !ok {
		t.Fatalf("ToMetricData returned ok=false")
	}
	if metric.ComponentName != PositronAgentComponentName {
		t.Errorf("ComponentName = %q, want %q", metric.ComponentName, PositronAgentComponentName)
	}
	if metric.Zone != "" {
		t.Errorf("Zone = %q, want empty", metric.Zone)
	}
}
