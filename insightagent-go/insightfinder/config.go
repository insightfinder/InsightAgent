package insightfinder

import (
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"github.com/rs/zerolog/log"
	"path/filepath"
	"strconv"
	"strings"
)

const IF_SECTION_NAME = "insightfinder"

// IFConfig is a struct that holds the configuration for "insightfinder"
// section in the configuration file.
// SamplingInterval is the sampling interval in seconds
type IFConfig struct {
	UserName   string
	LicenseKey string
	Token      string

	SystemName  string
	ProjectName string

	CollectorType string
	ProjectType   string
	InstanceType  string
	CloudType     string
	DataType      string
	AgentType     string
	IsContainer   bool
	IsReplay      bool

	SamplingInterval int
	ChunkSizeKb      int
	IFUrl            string
	IFProxies        map[string]string
}

func GetConfigBool(p *configparser.ConfigParser,
	section string, param string, required bool, defVal bool) bool {
	defer func() {
		if r := recover(); r != nil {
			panic(fmt.Sprintf("Error reading config [%s][%s]: %v", section, param, r))
		}
	}()

	val := GetConfigValue(p, section, param, required)
	if val == "" {
		return defVal
	}
	return ToBool(val)
}

func GetConfigInt(p *configparser.ConfigParser,
	section string, param string, required bool, defVal int) int {
	defer func() {
		if r := recover(); r != nil {
			panic(fmt.Sprintf("Error reading config [%s][%s]: %v", section, param, r))
		}
	}()

	val := GetConfigValue(p, section, param, required)
	if val == "" {
		return defVal
	}
	return ToInt(val)
}

func GetConfigString(p *configparser.ConfigParser,
	section string, param string, required bool) string {
	defer func() {
		if r := recover(); r != nil {
			panic(fmt.Sprintf("Error reading config [%s][%s]: %v", section, param, r))
		}
	}()

	val := GetConfigValue(p, section, param, required)
	return ToString(val)
}

func GetConfigValue(p *configparser.ConfigParser,
	section string, param string, required bool) interface{} {
	result, err := p.Get(section, param)
	if err != nil && required {
		panic(err)
	}
	if result == "" && required {
		panic("Configuration is required.")
	}
	return result
}

func GetConfigFiles(configRelativePath string) []string {
	if configRelativePath == "" {
		// default value for configuration path
		configRelativePath = "conf.d"
	}
	configPath := AbsFilePath(configRelativePath)
	log.Info().Msgf("Reading config files from directory: %s", configPath)

	allConfigs, err := filepath.Glob(configPath + "/*.ini")
	if err != nil {
		panic(err)
	}
	if len(allConfigs) == 0 {
		panic(fmt.Sprintf("No config file found in %s", configPath))
	}
	return allConfigs
}

func GetIFConfig(p *configparser.ConfigParser) *IFConfig {
	var userName = GetConfigString(p, IF_SECTION_NAME, "user_name", true)
	var licenseKey = GetConfigString(p, IF_SECTION_NAME, "license_key", true)
	var token = GetConfigString(p, IF_SECTION_NAME, "token", false)

	var systemName = GetConfigString(p, IF_SECTION_NAME, "system_name", false)
	var projectName = GetConfigString(p, IF_SECTION_NAME, "project_name", true)
	var projectType = strings.ToUpper(GetConfigString(p, IF_SECTION_NAME, "project_type", true))
	var collectorType = GetConfigString(p, IF_SECTION_NAME, "collector_type", false)
	var cloudType = GetConfigString(p, IF_SECTION_NAME, "cloud_type", false)
	var dynamicMetricType = GetConfigString(p, IF_SECTION_NAME, "dynamic_metric_type", false)
	var isContainer = GetConfigBool(p, IF_SECTION_NAME, "containerize", false, false)
	var isReplay = strings.Contains(projectType, "REPLAY")

	var samplingIntervalStr = GetConfigString(p, IF_SECTION_NAME, "sampling_interval", false)
	var samplingInterval = 0
	var chunkSizeKb = GetConfigInt(p, IF_SECTION_NAME, "chunk_size_kb", false, 2048)

	var ifURL = GetConfigString(p, IF_SECTION_NAME, "if_url", false)
	var httpProxy = GetConfigString(p, IF_SECTION_NAME, "if_http_proxy", false)
	var httpsProxy = GetConfigString(p, IF_SECTION_NAME, "if_https_proxy", false)

	if !isValidProjectType(projectType) {
		panic(fmt.Sprintf("Incorrect project type %s. Please use the supported project types.", projectType))
	}

	if len(collectorType) == 0 {
		collectorType = DefaultCollectorType
		if len(collectorType) == 0 {
			panic(fmt.Sprintf("collector is not set, set it with -collector flag or [%s][collector_type] configuration.",
				IF_SECTION_NAME))
		}
	}
	collectorType = strings.ToLower(collectorType)

	var instanceType = "PrivateCloud"
	var dataType = getProjectDataType(projectType)
	var agentType = getProjectAgentType(projectType, isReplay, isContainer, dynamicMetricType)
	iType, cType := getProjectInstanceAndCloudType(collectorType)
	if len(iType) > 0 {
		instanceType = iType
	}
	if len(cType) > 0 {
		cloudType = cType
	}

	if len(cloudType) == 0 {
		cloudType = "PrivateCloud"
	}

	if strings.Contains(projectType, "METRIC") {
		if len(samplingIntervalStr) == 0 {
			panic(fmt.Sprintf("Configuration [%s][sampling_interval] is required for METRIC project!",
				IF_SECTION_NAME))
		}
	} else {
		// Set default for non-metric project
		samplingInterval = 10 * 60
	}
	if strings.HasSuffix(samplingIntervalStr, "s") {
		seconds, err := strconv.Atoi(samplingIntervalStr[:len(samplingIntervalStr)-1])
		if err != nil {
			panic(fmt.Sprintf("Invalid sampling interval %s", samplingIntervalStr))
		}
		samplingInterval = seconds
	} else {
		minutes, err := strconv.Atoi(samplingIntervalStr)
		if err != nil {
			panic(fmt.Sprintf("Invalid sampling interval %s", samplingIntervalStr))
		}
		samplingInterval = minutes * 60
	}

	if len(ifURL) == 0 {
		ifURL = "https://app.insightfinder.com"
	}
	ifProxies := make(map[string]string)
	if len(httpProxy) > 0 {
		ifProxies["http"] = httpProxy
	}
	if len(httpsProxy) > 0 {
		ifProxies["https"] = httpsProxy
	}

	ifConfig := IFConfig{
		UserName:   userName,
		LicenseKey: licenseKey,
		Token:      token,

		SystemName:  systemName,
		ProjectName: projectName,

		CollectorType: collectorType,
		ProjectType:   projectType,
		InstanceType:  instanceType,
		CloudType:     cloudType,
		DataType:      dataType,
		AgentType:     agentType,
		IsContainer:   isContainer,
		IsReplay:      isReplay,

		SamplingInterval: samplingInterval,
		ChunkSizeKb:      chunkSizeKb,

		IFUrl:     ifURL,
		IFProxies: ifProxies,
	}

	return &ifConfig
}
