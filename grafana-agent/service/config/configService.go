package config

import (
	"gopkg.in/yaml.v2"
	"log/slog"
	"os"
)

type Config struct {
	InsightFinder InsightFinderConfig    `yaml:"insightfinder"`
	Grafana       GrafanaConfig          `yaml:"grafana"`
	Projects      []ProjectConfig        `yaml:"projects"`
	Query         map[string]QueryConfig `yaml:"query"`
}

type InsightFinderConfig struct {
	URL              string `yaml:"url"`
	UserName         string `yaml:"userName"`
	LicenseKey       string `yaml:"licenseKey"`
	SamplingInterval string `yaml:"samplingInterval"`
	RunInterval      string `yaml:"runInterval"`
}

type GrafanaConfig struct {
	URL           string `yaml:"url"`
	Token         string `yaml:"token"`
	DataSourceUID string `yaml:"dataSourceUID"`
	QueryDelay    string `yaml:"queryDelay"`
}

type ProjectConfig struct {
	Name        string   `yaml:"name"`
	Type        string   `yaml:"type"`
	IsContainer bool     `yaml:"isContainer"`
	System      string   `yaml:"system"`
	Query       []string `yaml:"query"`
}

type QueryConfig struct {
	MetricName       string
	Query            string   `yaml:"query"`
	InstanceLabel    []string `yaml:"instanceLabel"`
	ContainerLabel   []string `yaml:"containerLabel"`
	ComponentLabel   []string `yaml:"componentLabel"`
	UseRawMetricName bool     `yaml:"useRawMetricName"`
}

func LoadConfig() *Config {
	fileData, err := os.ReadFile("config.yaml")
	if err != nil {
		slog.Error("Failed to open config file: %v", err)
	}

	var config Config
	err = yaml.Unmarshal(fileData, &config)
	if err != nil {
		slog.Error("Failed to parse config file: %v", err)
	}

	// Add MetricName to QueryConfig
	for queryName, _ := range config.Query {
		queryConfig := config.Query[queryName]
		queryConfig.MetricName = queryName
		config.Query[queryName] = queryConfig
	}

	return &config
}
