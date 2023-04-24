package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"github.com/bigkevmcd/go-configparser"
)

var DEFAULT_MATADATE_MAX_INSTANCE = 1500

func absFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	absFilePath, err := filepath.Abs(filename)
	if err != nil {
		log.Fatal(err)
	}
	return absFilePath
}

func isValidProjectType(projectType string) bool {
	switch projectType {
	case
		"METRIC",
		"METRICREPLAY",
		"LOG",
		"LOGREPLAY",
		"INCIDENT",
		"INCIDENTREPLAY",
		"ALERT",
		"ALERTREPLAY",
		"DEPLOYMENT",
		"DEPLOYMENTREPLAY",
		"TRACE",
		"TRAVEREPLAY":
		return true
	}
	return false
}

func getConfigValue(p *configparser.ConfigParser, section string, param string, required bool) interface{} {
	result, err := p.Get(section, param)
	if err != nil && required {
		log.Fatal(err)
	}
	if result == "" && required {
		log.Fatal("InsightFinder configuration [", param, "] is required!")
	}
	return result
}

func getIFConfigs(configPath string) map[string]interface{} {
	log.Output(2, "Parsing the config file: "+configPath)
	p, err := configparser.NewConfigParserFromFile(configPath)
	if err != nil {
		log.Fatal(err)
	}

	// Required parameters
	var userName = getConfigValue(p, "insightfinder", "user_name", true).(string)
	var licenseKey = getConfigValue(p, "insightfinder", "license_key", true).(string)
	var projectName = getConfigValue(p, "insightfinder", "project_name", true).(string)
	var projectType = getConfigValue(p, "insightfinder", "project_type", true).(string)
	var runInterval = getConfigValue(p, "insightfinder", "run_interval", true).(string)

	// Optional parameters
	var token = getConfigValue(p, "insightfinder", "token", false).(string)
	var systemName = getConfigValue(p, "insightfinder", "system_name", false).(string)
	var projectNamePrefix = getConfigValue(p, "insightfinder", "project_name_prefix", false).(string)
	var metaDataMaxInstance = getConfigValue(p, "insightfinder", "metadata_max_instances", false).(string)
	var samplingInterval = getConfigValue(p, "insightfinder", "sampling_interval", false).(string)
	var ifURL = getConfigValue(p, "insightfinder", "if_url", false).(string)
	var httpProxy = getConfigValue(p, "insightfinder", "if_http_proxy", false).(string)
	var httpsProxy = getConfigValue(p, "insightfinder", "if_https_proxy", false).(string)
	var isReplay = getConfigValue(p, "insightfinder", "isReplay", false).(string)

	if len(projectNamePrefix) > 0 && !strings.HasSuffix(projectNamePrefix, "-") {
		projectNamePrefix = projectNamePrefix + "-"
	}

	if !isValidProjectType(projectType) {
		log.Fatal("Non-existing project type: ", projectType, "! Please use the supported project types. ")
	}

	if len(samplingInterval) == 0 {
		if strings.Contains(projectType, "METRIC") {
			log.Fatal("InsightFinder configuration [sampling_interval] is required for METRIC project!")
		} else {
			// Set default for non-metric project
			samplingInterval = "10"
		}
	}

	if strings.HasSuffix(samplingInterval, "s") {
		samplingInterval = samplingInterval[:len(samplingInterval)-1]
	} else {
		samplingIntervalInt, err := strconv.Atoi(samplingInterval)
		if err != nil {
			log.Fatal(err)
		}
		samplingInterval = string(rune(samplingIntervalInt * 60))
	}

	isReplay = strconv.FormatBool(strings.Contains(projectType, "REPLAY"))

	if len(metaDataMaxInstance) == 0 {
		metaDataMaxInstance = strconv.FormatInt(int64(DEFAULT_MATADATE_MAX_INSTANCE), 10)
	} else {
		metaDataMaxInstanceInt, err := strconv.Atoi(metaDataMaxInstance)
		if err != nil {
			log.Output(2, err.Error())
			log.Output(2, "Meta data max instance can only be integer number.")
			os.Exit(1)
		}
		if metaDataMaxInstanceInt > DEFAULT_MATADATE_MAX_INSTANCE {
			metaDataMaxInstance = string(rune(metaDataMaxInstanceInt))
		}
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

	configIF := map[string]interface{}{
		"userName":            userName,
		"licenseKey":          licenseKey,
		"token":               token,
		"projectName":         projectName,
		"systemName":          systemName,
		"projectNamePrefix":   projectNamePrefix,
		"projectType":         projectType,
		"metaDataMaxInstance": metaDataMaxInstance,
		"samplingInterval":    samplingInterval,
		"runInterval":         runInterval,
		"ifURL":               ifURL,
		"ifProxies":           ifProxies,
		"isReplay":            isReplay,
	}
	return configIF
}

func getConfigFiles(configRelativePath string) []string {
	if configRelativePath == "" {
		// default value for configuration path
		configRelativePath = "conf.d"
	}
	configPath := absFilePath(configRelativePath)
	log.Output(2, "Reading config files from directory: "+configPath)
	allConfigs, err := filepath.Glob(configPath + "/*.ini")
	if err != nil {
		log.Fatal(err)
	}
	if len(allConfigs) == 0 {
		log.Fatal("No config file found in", configPath)
	}
	return allConfigs
}

func workerProcess(configPath string, wg *sync.WaitGroup) {
	defer wg.Done()
	var IFconfig = getIFConfigs(configPath)

	fmt.Println(IFconfig)
}

func main() {
	allConfigs := getConfigFiles("")
	wg := new(sync.WaitGroup)
	numOfConfigs := len(allConfigs)
	wg.Add(numOfConfigs)
	for i := 0; i < numOfConfigs; i++ {
		go workerProcess(allConfigs[i], wg)
	}
	wg.Wait()
}
