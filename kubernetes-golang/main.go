package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

var DEFAULT_MATADATE_MAX_INSTANCE = 1500
var projectEndpoint = "api/v1/check-and-add-custom-project"
var IFSectionName = "insightfinder"

func getIFConfigsSection(p *configparser.ConfigParser) map[string]interface{} {

	// Required parameters
	var userName = GetConfigValue(p, IFSectionName, "user_name", true).(string)
	var licenseKey = GetConfigValue(p, IFSectionName, "license_key", true).(string)
	var projectName = GetConfigValue(p, IFSectionName, "project_name", true).(string)
	// We use uppercase for project log type.
	var projectType = strings.ToUpper(GetConfigValue(p, IFSectionName, "project_type", true).(string))
	var runInterval = GetConfigValue(p, IFSectionName, "run_interval", true).(string)

	// Optional parameters
	var token = GetConfigValue(p, IFSectionName, "token", false).(string)
	var systemName = GetConfigValue(p, IFSectionName, "system_name", false).(string)
	var projectNamePrefix = GetConfigValue(p, IFSectionName, "project_name_prefix", false).(string)
	var metaDataMaxInstance = GetConfigValue(p, IFSectionName, "metadata_max_instances", false).(string)
	var samplingInterval = GetConfigValue(p, IFSectionName, "sampling_interval", false).(string)
	var ifURL = GetConfigValue(p, IFSectionName, "if_url", false).(string)
	var httpProxy = GetConfigValue(p, IFSectionName, "if_http_proxy", false).(string)
	var httpsProxy = GetConfigValue(p, IFSectionName, "if_https_proxy", false).(string)
	var isReplay = GetConfigValue(p, IFSectionName, "isReplay", false).(string)

	if len(projectNamePrefix) > 0 && !strings.HasSuffix(projectNamePrefix, "-") {
		projectNamePrefix = projectNamePrefix + "-"
	}

	if !IsValidProjectType(projectType) {
		log.Fatal("[ERROR] Non-existing project type: " + projectType + "! Please use the supported project types. ")
	}

	if len(samplingInterval) == 0 {
		if strings.Contains(projectType, "METRIC") {
			log.Fatal("[ERROR] InsightFinder configuration [sampling_interval] is required for METRIC project!")
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
			log.Output(2, "[ERROR] Meta data max instance can only be integer number.")
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
	configPath := AbsFilePath(configRelativePath)
	log.Output(2, "Reading config files from directory: "+configPath)
	allConfigs, err := filepath.Glob(configPath + "/*.ini")
	if err != nil {
		log.Fatal(err)
	}
	if len(allConfigs) == 0 {
		log.Fatal("[ERROR] No config file found in", configPath)
	}
	return allConfigs
}

func checkProject(IFconfig map[string]interface{}) {
	projectName := IFconfig["projectName"].(string)
	if len(projectName) > 0 {
		if !isProjectExist(IFconfig) {
			log.Output(1, fmt.Sprintf("Didn't find the project named %s. Start creating project in the InsightFinder.", projectName))
			createProject(IFconfig)
			log.Output(1, "Sleep for 5 seconds to wait for project creation and will check the project exisitense again.")
			time.Sleep(time.Second * 5)
			if !isProjectExist(IFconfig) {
				log.Fatal("[ERROR] Fail to create project " + projectName)
			}
			log.Output(1, fmt.Sprintf("Create project %s successfully!", projectName))
		} else {
			log.Output(1, fmt.Sprintf("Project named %s exist. Program will continue.", projectName))
		}
	}
}

func isProjectExist(IFconfig map[string]interface{}) bool {
	projectName := IFconfig["projectName"].(string)
	log.Output(1, fmt.Sprintf("Check if the project named %s exists in the InsightFinder.", projectName))
	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", IFconfig["userName"].(string))
	form.Add("licenseKey", IFconfig["licenseKey"].(string))
	form.Add("projectName", projectName)
	headers := map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	}
	response := SendRequest(
		"POST",
		FormCompleteURL(IFconfig["ifURL"].(string), projectEndpoint),
		strings.NewReader(form.Encode()),
		headers,
	)
	println(string(response))
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	if !result["success"].(bool) {
		log.Fatal("Check project exist failed. Please check your parameters.")
	}

	return result["isProjectExist"].(bool)
}

func createProject(IFconfig map[string]interface{}) {
	projectName := IFconfig["projectName"].(string)
	log.Output(1, fmt.Sprintf("Check if the project named %s exists in the InsightFinder.", projectName))
	form := url.Values{}

	form.Add("operation", "create")
	form.Add("userName", IFconfig["userName"].(string))
	form.Add("licenseKey", IFconfig["licenseKey"].(string))
	form.Add("projectName", projectName)

	if IFconfig["systemName"] != nil {
		form.Add("systemName", IFconfig["systemName"].(string))
	} else {
		form.Add("systemName", projectName)
	}
	form.Add("instanceType", "PrivateCloud")
	form.Add("projectCloudType", "PrivateCloud")
	form.Add("dataType", ProjectTypeToDataType(projectName))
	form.Add("insightAgentType", ProjectTypeToAgentType(projectName, false))
	form.Add("samplingInterval", IFconfig["samplingInterval"].(string))
	samplingIntervalINT, err := strconv.Atoi(IFconfig["samplingInterval"].(string))
	if err != nil {
		log.Fatal(err)
	}
	form.Add("samplingIntervalInSeconds", fmt.Sprint(samplingIntervalINT*60))
	headers := map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	}
	response := SendRequest(
		"POST",
		FormCompleteURL(IFconfig["ifURL"].(string), projectEndpoint),
		strings.NewReader(form.Encode()),
		headers,
	)
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	log.Output(1, result["message"].(string))
}

func getInputSectionData(p *configparser.ConfigParser) interface{} {
	allSections := p.Sections()
	var data interface{}
	for i := 0; i < len(allSections); i++ {
		switch allSections[i] {
		case "powerFlex":
			data = PowerFlexDataStream(p)
		}
	}
	return data
}

func workerProcess(configPath string, wg *sync.WaitGroup) {
	defer wg.Done()
	log.Output(2, "Parsing the config file: "+configPath)
	p, err := configparser.NewConfigParserFromFile(configPath)
	if err != nil {
		log.Fatal(err)
	}
	var IFconfig = getIFConfigsSection(p)
	checkProject(IFconfig)
	data := getInputSectionData(p)
	SendMetricDataToIF(data, IFconfig)
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
