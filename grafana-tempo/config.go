package main

import (
	"fmt"
	"os"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

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

type AgentConfig struct {
	Interval  Duration `yaml:"interval"`
	Delay     Duration `yaml:"delay"`
	StartTime string   `yaml:"start_time"`
	EndTime   string   `yaml:"end_time"`
	Workers   int      `yaml:"workers"`
	StateFile string   `yaml:"state_file"`
}

type Config struct {
	Tempo         TempoConfig         `yaml:"tempo"`
	InsightFinder InsightFinderConfig `yaml:"insightfinder"`
	Agent         AgentConfig         `yaml:"agent"`

	startTime time.Time
	endTime   time.Time
}

func LoadConfig(path string) (*Config, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	cfg := &Config{}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	if err := cfg.applyDefaults(); err != nil {
		return nil, err
	}
	return cfg, nil
}

func (c *Config) applyDefaults() error {
	c.Tempo.Endpoint = strings.TrimRight(c.Tempo.Endpoint, "/")
	if c.Tempo.Endpoint == "" {
		return fmt.Errorf("tempo.endpoint is required")
	}
	if c.Tempo.Query == "" {
		c.Tempo.Query = "{}"
	}
	if c.Tempo.Limit <= 0 {
		c.Tempo.Limit = 500
	}
	if c.Tempo.SpansPerSpanSet <= 0 {
		c.Tempo.SpansPerSpanSet = 1
	}
	if c.Tempo.Timeout.Duration <= 0 {
		c.Tempo.Timeout.Duration = 30 * time.Second
	}

	if !c.InsightFinder.DryRun {
		missing := []string{}
		if c.InsightFinder.TraceServer == "" {
			missing = append(missing, "trace_server")
		}
		if c.InsightFinder.Username == "" {
			missing = append(missing, "username")
		}
		if c.InsightFinder.LicenseKey == "" {
			missing = append(missing, "license_key")
		}
		if c.InsightFinder.ProjectName == "" {
			missing = append(missing, "project_name")
		}
		if len(missing) > 0 {
			return fmt.Errorf("insightfinder.%s is required unless dry_run is true", strings.Join(missing, ", insightfinder."))
		}
	}

	if c.Agent.Interval.Duration <= 0 {
		c.Agent.Interval.Duration = time.Minute
	}
	if c.Agent.Delay.Duration < 0 {
		return fmt.Errorf("agent.delay must not be negative")
	}
	if c.Agent.Delay.Duration == 0 {
		c.Agent.Delay.Duration = 2 * time.Minute
	}
	if c.Agent.Workers <= 0 {
		c.Agent.Workers = 5
	}
	if c.Agent.StartTime != "" {
		t, err := time.Parse(time.RFC3339, c.Agent.StartTime)
		if err != nil {
			return fmt.Errorf("agent.start_time must be RFC3339: %w", err)
		}
		c.startTime = t
	}
	if c.Agent.EndTime != "" {
		t, err := time.Parse(time.RFC3339, c.Agent.EndTime)
		if err != nil {
			return fmt.Errorf("agent.end_time must be RFC3339: %w", err)
		}
		c.endTime = t
	}
	if !c.startTime.IsZero() && !c.endTime.IsZero() && !c.endTime.After(c.startTime) {
		return fmt.Errorf("agent.end_time must be after agent.start_time")
	}
	return nil
}
