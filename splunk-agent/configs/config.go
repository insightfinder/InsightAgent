package configs

import (
	"fmt"
	"os"
	"time"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v2"
)

// LoadConfig reads and validates the YAML config file at path.
func LoadConfig(path string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", path)

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	setDefaults(&cfg)
	if err := validate(&cfg); err != nil {
		return nil, fmt.Errorf("config validation: %w", err)
	}

	logrus.Info("Configuration loaded successfully")
	return &cfg, nil
}

func setDefaults(cfg *Config) {
	if cfg.Agent.LogLevel == "" {
		cfg.Agent.LogLevel = "INFO"
	}
	if cfg.Agent.Mode == "" {
		cfg.Agent.Mode = "continuous"
	}
	if cfg.Agent.ChunkInterval == 0 {
		cfg.Agent.ChunkInterval = 60 // 60 minutes default for historical chunks
	}

	if cfg.Splunk.MaxRetries == 0 {
		cfg.Splunk.MaxRetries = 3
	}
	if cfg.Splunk.QueryTimeout == 0 {
		cfg.Splunk.QueryTimeout = 60
	}
	if cfg.Splunk.MaxResults == 0 {
		cfg.Splunk.MaxResults = 5000
	}
	for i := range cfg.Splunk.Queries {
		if cfg.Splunk.Queries[i].MaxResults == 0 {
			cfg.Splunk.Queries[i].MaxResults = cfg.Splunk.MaxResults
		}
	}

	if cfg.InsightFinder.ServerURL == "" {
		cfg.InsightFinder.ServerURL = "https://app.insightfinder.com"
	}
	if cfg.InsightFinder.LogsProjectType == "" {
		cfg.InsightFinder.LogsProjectType = "LOG"
	}
	if cfg.InsightFinder.SamplingInterval == 0 {
		cfg.InsightFinder.SamplingInterval = 60
	}
	if cfg.InsightFinder.CloudType == "" {
		cfg.InsightFinder.CloudType = "OnPremise"
	}
	if cfg.InsightFinder.InstanceType == "" {
		cfg.InsightFinder.InstanceType = "OnPremise"
	}
	if cfg.InsightFinder.ChunkSize == 0 {
		cfg.InsightFinder.ChunkSize = 2 * 1024 * 1024 // 2 MB
	}
	if cfg.InsightFinder.MaxPacketSize == 0 {
		cfg.InsightFinder.MaxPacketSize = 10 * 1024 * 1024 // 10 MB
	}
	if cfg.InsightFinder.RetryTimes == 0 {
		cfg.InsightFinder.RetryTimes = 3
	}
	if cfg.InsightFinder.RetryInterval == 0 {
		cfg.InsightFinder.RetryInterval = 5
	}

	// Default field mappings: host → tag, sourcetype → component.
	// Only apply the built-in default when neither a field name nor a static
	// value has been explicitly configured, so an empty string in the YAML
	// means "no mapping" rather than silently overriding.
	if cfg.InsightFinder.TagField == "" && cfg.InsightFinder.TagValue == "" {
		cfg.InsightFinder.TagField = "host"
	}
	if cfg.InsightFinder.ComponentField == "" && cfg.InsightFinder.ComponentValue == "" {
		cfg.InsightFinder.ComponentField = "sourcetype"
	}
}

func validate(cfg *Config) error {
	if cfg.Splunk.ServerURL == "" {
		return fmt.Errorf("splunk.server_url is required")
	}
	if cfg.Splunk.Token == "" && (cfg.Splunk.Username == "" || cfg.Splunk.Password == "") {
		return fmt.Errorf("splunk: provide either token (Splunk Cloud) or username + password (Enterprise)")
	}
	if len(cfg.Splunk.Queries) == 0 {
		return fmt.Errorf("splunk.queries: at least one query must be configured")
	}
	for i, q := range cfg.Splunk.Queries {
		if q.Name == "" {
			return fmt.Errorf("splunk.queries[%d]: name is required", i)
		}
		if q.Query == "" {
			return fmt.Errorf("splunk.queries[%d] (%s): query is required", i, q.Name)
		}
	}

	// InsightFinder credentials are not needed for download-only historical mode.
	if cfg.Agent.Mode != "historical" {
		if cfg.InsightFinder.UserName == "" {
			return fmt.Errorf("insightfinder.username is required")
		}
		if cfg.InsightFinder.LicenseKey == "" {
			return fmt.Errorf("insightfinder.license_key is required")
		}
		if cfg.InsightFinder.LogsProjectName == "" {
			return fmt.Errorf("insightfinder.logs_project_name is required")
		}
	}

	// Validate mode-specific fields.
	switch cfg.Agent.Mode {
	case "continuous", "":
		// no additional validation needed
	case "historical":
		if cfg.Agent.StartTime == "" {
			return fmt.Errorf("agent.start_time is required for mode 'historical'")
		}
		if _, err := ParseAgentTime(cfg.Agent.StartTime); err != nil {
			return fmt.Errorf("invalid agent.start_time '%s': %v", cfg.Agent.StartTime, err)
		}
		if cfg.Agent.EndTime != "" {
			if _, err := ParseAgentTime(cfg.Agent.EndTime); err != nil {
				return fmt.Errorf("invalid agent.end_time '%s': %v", cfg.Agent.EndTime, err)
			}
		}
		if cfg.Agent.DownloadPath == "" {
			return fmt.Errorf("agent.download_path is required for mode 'historical'")
		}
	default:
		return fmt.Errorf("invalid agent.mode '%s': must be 'continuous' or 'historical'", cfg.Agent.Mode)
	}

	return nil
}

// ParseAgentTime parses a time string in RFC3339 or date-only ("2006-01-02") format.
func ParseAgentTime(s string) (time.Time, error) {
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02", s); err == nil {
		return t, nil
	}
	return time.Time{}, fmt.Errorf("unsupported time format; use RFC3339 (e.g. '2024-01-01T00:00:00Z') or date-only ('2024-01-01')")
}
