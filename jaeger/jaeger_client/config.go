package jaeger_client

import (
	"log/slog"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type JaegerYAMLConfigFile struct {
	Jaeger struct {
		Endpoint    string            `yaml:"endpoint"`
		Service     string            `yaml:"service"`
		Operation   string            `yaml:"operation"`
		Tags        []JaegerQueryTags `yaml:"tags"`
		MaxDuration string            `yaml:"max_duration"`
		MinDuration string            `yaml:"min_duration"`
		Step        string            `yaml:"step"`
		Limit       int               `yaml:"limit"`
		Range       string            `yaml:"range"`
	} `yaml:"jaeger"`
}

type JaegerQueryTags struct {
	Key   string `yaml:"key"`
	Value string `yaml:"value"`
}

func CreateJaegerClientFromConfig(filename string) *JaegerClient {
	// Create a new Jaeger client from the YAML config file
	yamlFile, err := os.ReadFile(filename)
	if err != nil {
		slog.Error("Error reading YAML file: ", err)
		panic(err)
	}

	// Parse the YAML file
	var config JaegerYAMLConfigFile
	err = yaml.Unmarshal(yamlFile, &config)
	if err != nil {
		slog.Error("Error parsing YAML file: ", err)
		panic(err)
	}

	// Generate StartTime and EndTime
	timeRange := config.Jaeger.Range
	endTime := time.Now()
	startTime := endTime
	duration, err := time.ParseDuration(timeRange)
	if err != nil {
		slog.Error("Error parsing time duration: ", err)
		panic(err)
	}
	startTime = time.Now().Add(-duration)

	// Generate other time.time fields
	if config.Jaeger.Step == "" {
		slog.Warn("Step is not defined in the config file, default to 30s")
		config.Jaeger.Step = "30s"
	}
	step, err := time.ParseDuration(config.Jaeger.Step)
	if err != nil {
		slog.Error("Error parsing time step: ", err)
		panic(err)
	}

	// Create a new Jaeger client from the YAML config file
	newJC := &JaegerClient{
		Endpoint:    config.Jaeger.Endpoint,
		Service:     config.Jaeger.Service,
		Operation:   config.Jaeger.Operation,
		Limit:       config.Jaeger.Limit,
		MaxDuration: config.Jaeger.MaxDuration,
		MinDuration: config.Jaeger.MinDuration,
		StartTime:   startTime,
		EndTime:     endTime,
		Step:        step,
	}

	return newJC
}
