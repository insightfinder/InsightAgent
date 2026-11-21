package config

import (
	"fmt"
	"net/url"
	"os"
	"strings"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"
)

func LoadConfig(configPath string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", configPath)

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read YAML file: %v", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse YAML file: %v", err)
	}

	setDefaults(&config)
	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %v", err)
	}

	logrus.Info("Configuration loaded successfully")
	return &config, nil
}

func setDefaults(config *Config) {
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "INFO"
	}

	if config.ServiceNow.TimeoutSec == 0 {
		config.ServiceNow.TimeoutSec = 60
	}
	if config.ServiceNow.MaxRetries <= 0 {
		config.ServiceNow.MaxRetries = 10
	}
	if config.ServiceNow.RetryIntervalSec <= 0 {
		config.ServiceNow.RetryIntervalSec = 10
	}
	if config.ServiceNow.ShortDescription == "" {
		config.ServiceNow.ShortDescription = "InsightFinder ServiceNow health check - test incident"
	}
	for i := range config.ServiceNow.Instances {
		inst := &config.ServiceNow.Instances[i]
		inst.URL = strings.TrimRight(strings.TrimSpace(inst.URL), "/")
		if inst.Name == "" {
			inst.Name = instanceNameFromURL(inst.URL)
		}
	}

	if !strings.HasPrefix(config.InsightFinder.ServerURL, "http") && config.InsightFinder.ServerURL != "" {
		config.InsightFinder.ServerURL = "https://" + config.InsightFinder.ServerURL
	}
	config.InsightFinder.ServerURL = strings.TrimRight(config.InsightFinder.ServerURL, "/")
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 1800 // 30 minutes
	}
	if config.InsightFinder.CloudType == "" {
		config.InsightFinder.CloudType = "OnPremise"
	}
	if config.InsightFinder.InstanceType == "" {
		config.InsightFinder.InstanceType = "OnPremise"
	}
	if config.InsightFinder.SystemName == "" {
		config.InsightFinder.SystemName = config.InsightFinder.ProjectName
	}
	if config.InsightFinder.ComponentName == "" {
		config.InsightFinder.ComponentName = "ServiceNow"
	}
}

func validateConfig(config *Config) error {
	if config.InsightFinder.ServerURL == "" {
		return fmt.Errorf("insightfinder server_url is required")
	}
	if config.InsightFinder.UserName == "" {
		return fmt.Errorf("insightfinder username is required")
	}
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder license_key is required")
	}
	if config.InsightFinder.ProjectName == "" {
		return fmt.Errorf("insightfinder project_name is required")
	}

	seen := map[string]bool{}
	for _, inst := range config.ServiceNow.Instances {
		if !inst.Enabled {
			continue
		}
		if inst.URL == "" || inst.Username == "" || inst.Password == "" {
			return fmt.Errorf("servicenow instance %q requires url, username and password", inst.Name)
		}
		if seen[inst.Name] {
			return fmt.Errorf("duplicate servicenow instance name %q", inst.Name)
		}
		seen[inst.Name] = true
	}
	if len(seen) == 0 {
		return fmt.Errorf("no enabled servicenow instances configured")
	}

	return nil
}

// instanceNameFromURL returns the first label of the host, e.g.
// https://dev428447.service-now.com -> dev428447.
func instanceNameFromURL(raw string) string {
	u, err := url.Parse(raw)
	if err != nil || u.Hostname() == "" {
		return raw
	}
	return strings.SplitN(u.Hostname(), ".", 2)[0]
}
