package config

import (
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"
)

func LoadConfig(configPath string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", configPath)

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	setDefaults(&config)
	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %w", err)
	}

	logrus.Info("Configuration loaded successfully")
	return &config, nil
}

func setDefaults(config *Config) {
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "INFO"
	}
	if config.Agent.Interval.Duration <= 0 {
		config.Agent.Interval.Duration = time.Minute
	}
	if config.Agent.Delay.Duration == 0 {
		config.Agent.Delay.Duration = 2 * time.Minute
	}
	if config.Agent.Workers <= 0 {
		config.Agent.Workers = 5
	}

	config.Tempo.Endpoint = strings.TrimRight(config.Tempo.Endpoint, "/")
	if config.Tempo.Query == "" {
		config.Tempo.Query = "{}"
	}
	if config.Tempo.Limit <= 0 {
		config.Tempo.Limit = 500
	}
	if config.Tempo.SpansPerSpanSet <= 0 {
		config.Tempo.SpansPerSpanSet = 1
	}
	if config.Tempo.Timeout.Duration <= 0 {
		config.Tempo.Timeout.Duration = 30 * time.Second
	}
}

func validateConfig(config *Config) error {
	if _, err := logrus.ParseLevel(config.Agent.LogLevel); err != nil {
		return fmt.Errorf("agent.log_level: %w", err)
	}
	if config.Agent.Delay.Duration < 0 {
		return fmt.Errorf("agent.delay must not be negative")
	}
	if config.Agent.StartTime != "" {
		t, err := time.Parse(time.RFC3339, config.Agent.StartTime)
		if err != nil {
			return fmt.Errorf("agent.start_time must be RFC3339: %w", err)
		}
		config.Agent.Start = t
	}
	if config.Agent.EndTime != "" {
		t, err := time.Parse(time.RFC3339, config.Agent.EndTime)
		if err != nil {
			return fmt.Errorf("agent.end_time must be RFC3339: %w", err)
		}
		config.Agent.End = t
	}
	if !config.Agent.Start.IsZero() && !config.Agent.End.IsZero() && !config.Agent.End.After(config.Agent.Start) {
		return fmt.Errorf("agent.end_time must be after agent.start_time")
	}

	if config.Tempo.Endpoint == "" {
		return fmt.Errorf("tempo.endpoint is required")
	}

	if !config.InsightFinder.DryRun {
		missing := []string{}
		if config.InsightFinder.TraceServer == "" {
			missing = append(missing, "insightfinder.trace_server")
		}
		if config.InsightFinder.Username == "" {
			missing = append(missing, "insightfinder.username")
		}
		if config.InsightFinder.LicenseKey == "" {
			missing = append(missing, "insightfinder.license_key")
		}
		if config.InsightFinder.ProjectName == "" {
			missing = append(missing, "insightfinder.project_name")
		}
		if len(missing) > 0 {
			return fmt.Errorf("%s required unless insightfinder.dry_run is true", strings.Join(missing, ", "))
		}
	}
	return nil
}
