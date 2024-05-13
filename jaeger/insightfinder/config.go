package insightfinder

import (
	"log/slog"
	"os"

	"gopkg.in/yaml.v3"
)

type InsightFinderYAMLConfigFile struct {
	InsightFinder struct {
		Endpoint    string `yaml:"endpoint"`
		Username    string `yaml:"username"`
		LicenseKey  string `yaml:"license_key"`
		ProjectName string `yaml:"project_name"`
		ProjectType string `yaml:"project_type"`
		IsContainer bool   `yaml:"is_container"`
		SystemName  string `yaml:"system_name"`
	} `yaml:"insightfinder"`
}

/*
NewInsightFinderFromYAML creates a new InsightFinder client from a YAML config file
@param configFile: The path to the YAML config file
@return InsightFinder: The InsightFinder client
*/
func NewInsightFinderFromYAML(configFile string) *InsightFinder {

	// Read the YAML file
	yamlFile, err := os.ReadFile(configFile)
	if err != nil {
		slog.Error("Error reading YAML file: ", err)
		panic(err)
	}

	// Parse the YAML file
	var config InsightFinderYAMLConfigFile
	err = yaml.Unmarshal(yamlFile, &config)
	if err != nil {
		slog.Error("Error parsing YAML file: ", err)
		panic(err)
	}

	// Create a new InsightFinder client from the YAML config file
	newIF := NewInsightFinder(
		config.InsightFinder.Endpoint,
		config.InsightFinder.Username,
		config.InsightFinder.LicenseKey,
		config.InsightFinder.ProjectName,
		config.InsightFinder.ProjectType,
		config.InsightFinder.SystemName,
	)

	return &newIF
}
