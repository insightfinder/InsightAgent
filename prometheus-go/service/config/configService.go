package config

import (
	"log/slog"
	"os"

	"gopkg.in/yaml.v2"
)

type Config struct {
	InsightFinder InsightFinderConfig    `yaml:"insightfinder"`
	Prometheus    PrometheusConfig       `yaml:"prometheus"`
	Projects      []ProjectConfig        `yaml:"projects"`
	Query         map[string]QueryConfig `yaml:"query"`
}

type InsightFinderConfig struct {
	URL              string `yaml:"url"`
	UserName         string `yaml:"userName"`
	LicenseKey       string `yaml:"licenseKey"`
	SamplingInterval string `yaml:"samplingInterval"`
	RunInterval      string `yaml:"runInterval"`
	HttpProxy        string `yaml:"ifHttpProxy"`
	HttpsProxy       string `yaml:"ifHttpsProxy"`
}

type PrometheusConfig struct {
	URL         string `yaml:"url"`
	Username    string `yaml:"username"`
	Password    string `yaml:"password"`
	VerifyCerts bool   `yaml:"verifyCerts"`
	CACert      string `yaml:"caCert"`
	ClientCert  string `yaml:"clientCert"`
	ClientKey   string `yaml:"clientKey"`
	QueryDelay  string `yaml:"queryDelay"`
	HttpProxy   string `yaml:"agentHttpProxy"`
	HttpsProxy  string `yaml:"agentHttpsProxy"`
	Timeout     string `yaml:"timeout"`
}

type ProjectConfig struct {
	Name                 string   `yaml:"name"`
	System               string   `yaml:"system"`
	Type                 string   `yaml:"type"`
	IsContainer          bool     `yaml:"isContainer"`
	DynamicMetricType    string   `yaml:"dynamicMetricType"`
	Query                []string `yaml:"query"`
	HistTimeRange        string   `yaml:"histTimeRange"`
	DefaultInsanceName   string   `yaml:"defaultInstanceName"`
	DefaultComponentName string   `yaml:"defaultComponentName"`
	DefaultContainerName string   `yaml:"defaultContainerName"`
}

type QueryConfig struct {
	MetricName     string
	Queries        string   `yaml:"queries"`
	InstanceLabel  []string `yaml:"instanceLabel"`
	ComponentLabel []string `yaml:"componentLabel"`
	ContainerLabel []string `yaml:"containerLabel"`
	TimestampLabel []string `yaml:"timestampLabel"`
	// UseRawMetricName bool     `yaml:"useRawMetricName"`
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
