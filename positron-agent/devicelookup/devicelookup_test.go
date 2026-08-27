package devicelookup

import "testing"

func TestZoneForWithFallback(t *testing.T) {
	va := VenueAbbrLookup{
		"mead": "Meadowbrook",
		"ssvl": "Sunset Valley",
	}

	tests := []struct {
		name       string
		ownName    string
		systemName string
		wantZone   string
		wantPrefix string
	}{
		{
			name:       "own name abbreviation matches, no fallback needed",
			ownName:    "MEAD-LMRV-RAD_C5-Res-Budgett-1253",
			systemName: "SSVL-2236SE100thLane-GAM",
			wantZone:   "Meadowbrook",
			wantPrefix: "",
		},
		{
			name:       "own name has no abbreviation prefix at all, falls back to system name",
			ownName:    "10075SE22ndPath-GN",
			systemName: "SSVL-2236SE100thLane-GAM",
			wantZone:   "Sunset Valley",
			wantPrefix: "SSVL",
		},
		{
			name:       "own name prefix doesn't match any registered abbreviation, falls back to system name",
			ownName:    "Unregistered-Device-1",
			systemName: "SSVL-2236SE100thLane-GAM",
			wantZone:   "Sunset Valley",
			wantPrefix: "SSVL",
		},
		{
			name:       "neither own name nor system name resolve",
			ownName:    "Unregistered-Device-1",
			systemName: "Unregistered-GAM",
			wantZone:   "",
			wantPrefix: "",
		},
		{
			name:       "system name has no abbreviation prefix either",
			ownName:    "10075SE22ndPath-GN",
			systemName: "SomeGAMWithNoDash",
			wantZone:   "",
			wantPrefix: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			zone, prefix := va.ZoneForWithFallback(tt.ownName, tt.systemName)
			if zone != tt.wantZone || prefix != tt.wantPrefix {
				t.Errorf("ZoneForWithFallback(%q, %q) = (%q, %q), want (%q, %q)",
					tt.ownName, tt.systemName, zone, prefix, tt.wantZone, tt.wantPrefix)
			}
		})
	}
}
