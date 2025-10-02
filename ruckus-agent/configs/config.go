package config

import (
	"fmt"
	"os"

	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"
)

func LoadConfig(configPath string) (*Config, error) {
	logrus.Infof("Loading configuration from: %s", configPath)

	// Check if file exists
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("configuration file does not exist: %s", configPath)
	}

	// Read YAML file
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read YAML file: %v", err)
	}

	var config Config

	// Parse YAML
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse YAML file: %v", err)
	}

	// Validate and set defaults
	setDefaults(&config)
	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("configuration validation failed: %v", err)
	}

	// Log active metric filters
	logMetricConfiguration(&config)

	logrus.Info("Configuration loaded successfully")
	return &config, nil
}

func setDefaults(config *Config) {
	// Ruckus defaults
	if config.Ruckus.ControllerPort == 0 {
		config.Ruckus.ControllerPort = 8443
	}
	if config.Ruckus.APIVersion == "" {
		config.Ruckus.APIVersion = "v10_0"
	}
	if config.Ruckus.MaxConcurrentRequests == 0 {
		config.Ruckus.MaxConcurrentRequests = 20
	}

	// Agent defaults
	if config.Agent.LogLevel == "" {
		config.Agent.LogLevel = "info"
	}

	// InsightFinder defaults - sampling_interval is now the main collection interval
	if config.InsightFinder.SamplingInterval == 0 {
		config.InsightFinder.SamplingInterval = 300 // 5 minutes default
	}
	if config.InsightFinder.CloudType == "" {
		config.InsightFinder.CloudType = "OnPremise"
	}
	if config.InsightFinder.InstanceType == "" {
		config.InsightFinder.InstanceType = "OnPremise"
	}
	if config.InsightFinder.ProjectType == "" {
		config.InsightFinder.ProjectType = "Metric"
	}
	if config.InsightFinder.SystemName == "" {
		config.InsightFinder.SystemName = config.InsightFinder.ProjectName
	}

	// MetricFilter defaults - all set to false by default
	config.MetricFilter.NumClientsTotal = false
	config.MetricFilter.NumClients24G = false
	config.MetricFilter.NumClients5G = false
	config.MetricFilter.NumClients6G = false
	config.MetricFilter.Airtime24G = false
	config.MetricFilter.Airtime5G = false
	config.MetricFilter.Airtime6G = false
	config.MetricFilter.RSSIAvg = false
	config.MetricFilter.SNRAvg = false
	config.MetricFilter.ClientsRSSIBelow74 = false
	config.MetricFilter.ClientsRSSIBelow78 = false
	config.MetricFilter.ClientsRSSIBelow80 = false
	config.MetricFilter.ClientsSNRBelow15 = false
	config.MetricFilter.ClientsSNRBelow18 = false
	config.MetricFilter.ClientsSNRBelow20 = false

	logrus.Debug("Default values applied to configuration")
}

func validateConfig(config *Config) error {
	if config.Ruckus.ControllerHost == "" {
		return fmt.Errorf("ruckus controller_host is required")
	}
	if config.Ruckus.Username == "" {
		return fmt.Errorf("ruckus username is required")
	}
	if config.Ruckus.Password == "" {
		return fmt.Errorf("ruckus password is required")
	}

	if config.InsightFinder.ServerURL == "" {
		return fmt.Errorf("insightfinder server_url is required")
	}
	if config.InsightFinder.UserName == "" {
		return fmt.Errorf("insightfinder username is required")
	}
	if config.InsightFinder.LicenseKey == "" {
		return fmt.Errorf("insightfinder license_key is required")
	}

	return nil
}

// logMetricConfiguration logs which metrics are enabled for streaming
func logMetricConfiguration(config *Config) {
	logrus.Info("Metric filtering configuration:")

	enabledMetrics := []string{}
	totalMetrics := 0

	// Client count metrics
	totalMetrics++
	if config.MetricFilter.NumClientsTotal {
		enabledMetrics = append(enabledMetrics, "Num Clients Total")
	}
	totalMetrics++
	if config.MetricFilter.NumClients24G {
		enabledMetrics = append(enabledMetrics, "Num Clients 24G")
	}
	totalMetrics++
	if config.MetricFilter.NumClients5G {
		enabledMetrics = append(enabledMetrics, "Num Clients 5G")
	}
	totalMetrics++
	if config.MetricFilter.NumClients6G {
		enabledMetrics = append(enabledMetrics, "Num Clients 6G")
	}

	// Airtime metrics
	totalMetrics++
	if config.MetricFilter.Airtime24G {
		enabledMetrics = append(enabledMetrics, "Airtime 24G Percent")
	}
	totalMetrics++
	if config.MetricFilter.Airtime5G {
		enabledMetrics = append(enabledMetrics, "Airtime 5G Percent")
	}
	totalMetrics++
	if config.MetricFilter.Airtime6G {
		enabledMetrics = append(enabledMetrics, "Airtime 6G Percent")
	}

	// Client-derived metrics
	totalMetrics++
	if config.MetricFilter.RSSIAvg {
		enabledMetrics = append(enabledMetrics, "RSSI Avg")
	}
	totalMetrics++
	if config.MetricFilter.SNRAvg {
		enabledMetrics = append(enabledMetrics, "SNR Avg")
	}
	totalMetrics++
	if config.MetricFilter.ClientsRSSIBelow74 {
		enabledMetrics = append(enabledMetrics, "% Clients RSSI < -74 dBm")
	}
	totalMetrics++
	if config.MetricFilter.ClientsRSSIBelow78 {
		enabledMetrics = append(enabledMetrics, "% Clients RSSI < -78 dBm")
	}
	totalMetrics++
	if config.MetricFilter.ClientsRSSIBelow80 {
		enabledMetrics = append(enabledMetrics, "% Clients RSSI < -80 dBm")
	}
	totalMetrics++
	if config.MetricFilter.ClientsSNRBelow15 {
		enabledMetrics = append(enabledMetrics, "% Clients SNR < 15 dBm")
	}
	totalMetrics++
	if config.MetricFilter.ClientsSNRBelow18 {
		enabledMetrics = append(enabledMetrics, "% Clients SNR < 18 dBm")
	}
	totalMetrics++
	if config.MetricFilter.ClientsSNRBelow20 {
		enabledMetrics = append(enabledMetrics, "% Clients SNR < 20 dBm")
	}

	logrus.Infof("Enabled metrics (%d/%d): %v", len(enabledMetrics), totalMetrics, enabledMetrics)
	if len(enabledMetrics) == 0 {
		logrus.Warn("No metrics are enabled for streaming! All metrics are set to false in configuration.")
	}
}
