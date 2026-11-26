package config

import (
	"fmt"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Agent         AgentConfig         `yaml:"agent"`
	Tempo         TempoConfig         `yaml:"tempo"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
}

type AgentConfig struct {
	LogLevel  string   `yaml:"log_level"`
	Interval  Duration `yaml:"interval"`
	Delay     Duration `yaml:"delay"`
	StartTime string   `yaml:"start_time"`
	EndTime   string   `yaml:"end_time"`
	Workers   int      `yaml:"workers"`
	StateFile string   `yaml:"state_file"`

	Start time.Time `yaml:"-"`
	End   time.Time `yaml:"-"`
}

type TempoConfig struct {
	Endpoint           string            `yaml:"endpoint"`
	Username           string            `yaml:"username"`
	Password           string            `yaml:"password"`
	TenantID           string            `yaml:"tenant_id"`
	Headers            map[string]string `yaml:"headers"`
	InsecureSkipVerify bool              `yaml:"insecure_skip_verify"`
	Query              string            `yaml:"query"`
	Limit              int               `yaml:"limit"`
	SpansPerSpanSet    int               `yaml:"spans_per_span_set"`
	Timeout            Duration          `yaml:"timeout"`
}

type InsightFinderConfig struct {
	TraceServer        string `yaml:"trace_server"`
	TLS                bool   `yaml:"tls"`
	InsecureSkipVerify bool   `yaml:"insecure_skip_verify"`
	Username           string `yaml:"username"`
	LicenseKey         string `yaml:"license_key"`
	ProjectName        string `yaml:"project_name"`
	SystemName         string `yaml:"system_name"`
	DryRun             bool   `yaml:"dry_run"`
}

type Duration struct {
	time.Duration
}

func (d *Duration) UnmarshalYAML(value *yaml.Node) error {
	parsed, err := time.ParseDuration(strings.TrimSpace(value.Value))
	if err != nil {
		return fmt.Errorf("invalid duration %q: %w", value.Value, err)
	}
	d.Duration = parsed
	return nil
}
