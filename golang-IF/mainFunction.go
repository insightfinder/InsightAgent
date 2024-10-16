package golangif

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

const DEFAULT_MATADATE_MAX_INSTANCE = 1500
const PROJECT_END_POINT = "api/v1/check-and-add-custom-project"
const IF_SECTION_NAME = "insightfinder"

func GetInsightFinderConfig(p *configparser.ConfigParser) map[string]interface{} {
	// Required parameters
	var userName = ToString(GetConfigValue(p, IF_SECTION_NAME, "user_name", true))
	var licenseKey = ToString(GetConfigValue(p, IF_SECTION_NAME, "license_key", true))
	var projectName = ToString(GetConfigValue(p, IF_SECTION_NAME, "project_name", true))
	// We use uppercase for project log type.
	var projectType = strings.ToUpper(ToString(GetConfigValue(p, IF_SECTION_NAME, "project_type", true)))
	var runInterval = ToString(GetConfigValue(p, IF_SECTION_NAME, "run_interval", true))
	// Optional parameters
	var token = ToString(GetConfigValue(p, IF_SECTION_NAME, "token", false))
	var systemName = ToString(GetConfigValue(p, IF_SECTION_NAME, "system_name", false))
	var projectNamePrefix = ToString(GetConfigValue(p, IF_SECTION_NAME, "project_name_prefix", false))
	var metaDataMaxInstance = ToString(GetConfigValue(p, IF_SECTION_NAME, "metadata_max_instances", false))
	var samplingInterval = ToString(GetConfigValue(p, IF_SECTION_NAME, "sampling_interval", false))
	var ifURL = ToString(GetConfigValue(p, IF_SECTION_NAME, "if_url", false))
	var httpProxy = ToString(GetConfigValue(p, IF_SECTION_NAME, "if_http_proxy", false))
	var httpsProxy = ToString(GetConfigValue(p, IF_SECTION_NAME, "if_https_proxy", false))
	var isReplay = ToString(GetConfigValue(p, IF_SECTION_NAME, "isReplay", false))
	var indexing = ToBool(GetConfigValue(p, IF_SECTION_NAME, "indexing", false))
	var samplingIntervalInSeconds string

	if len(projectNamePrefix) > 0 && !strings.HasSuffix(projectNamePrefix, "-") {
		projectNamePrefix = projectNamePrefix + "-"
	}
	if !IsValidProjectType(projectType) {
		panic("[ERROR] Non-existing project type: " + projectType + "! Please use the supported project types. ")
	}
	if len(samplingInterval) == 0 {
		if strings.Contains(projectType, "METRIC") {
			panic("[ERROR] InsightFinder configuration [sampling_interval] is required for METRIC project!")
		} else {
			// Set default for non-metric project
			samplingInterval = "10"
			samplingIntervalInSeconds = "600"
		}
	}

	if strings.HasSuffix(samplingInterval, "s") {
		samplingIntervalInSeconds = samplingInterval[:len(samplingInterval)-1]
		samplingIntervalInt, err := strconv.ParseFloat(samplingIntervalInSeconds, 32)
		if err != nil {
			panic(err)
		}
		samplingInterval = fmt.Sprint(samplingIntervalInt / 60.0)
	} else {
		samplingIntervalInt, err := strconv.Atoi(samplingInterval)
		if err != nil {
			panic(err)
		}
		samplingIntervalInSeconds = fmt.Sprint(int64(samplingIntervalInt * 60))
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
		"userName":                  userName,
		"licenseKey":                licenseKey,
		"token":                     token,
		"projectName":               projectName,
		"systemName":                systemName,
		"projectNamePrefix":         projectNamePrefix,
		"projectType":               projectType,
		"metaDataMaxInstance":       metaDataMaxInstance,
		"samplingInterval":          samplingInterval,
		"samplingIntervalInSeconds": samplingIntervalInSeconds,
		"runInterval":               runInterval,
		"ifURL":                     ifURL,
		"ifProxies":                 ifProxies,
		"isReplay":                  isReplay,
		"indexing":                  indexing,
	}
	return configIF
}

func CheckProject(IFconfig map[string]interface{}) {
	projectName := ToString(IFconfig["projectName"])
	if len(projectName) > 0 {
		if !isProjectExist(IFconfig) {
			log.Output(1, fmt.Sprintf("Didn't find the project named %s. Start creating project in the InsightFinder.", projectName))
			createProject(IFconfig)
			log.Output(1, "Sleep for 5 seconds to wait for project creation and will check the project exisitense again.")
			time.Sleep(time.Second * 5)
			if !isProjectExist(IFconfig) {
				panic("[ERROR] Fail to create project " + projectName)
			}
			log.Output(1, fmt.Sprintf("Create project %s successfully!", projectName))
		} else {
			log.Output(1, fmt.Sprintf("Project named %s exist. Program will continue.", projectName))
		}
	}
}

func isProjectExist(IFconfig map[string]interface{}) bool {
	projectName := ToString(IFconfig["projectName"])
	log.Output(1, fmt.Sprintf("Check if the project named %s exists in the InsightFinder.", projectName))
	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", ToString(IFconfig["userName"]))
	form.Add("licenseKey", ToString(IFconfig["licenseKey"]))
	form.Add("projectName", projectName)
	headers := map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	}
	response, _ := SendRequest(
		http.MethodPost,
		FormCompleteURL(ToString(IFconfig["ifURL"]), PROJECT_END_POINT),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{},
	)
	println(string(response))
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	if !ToBool(result["success"]) {
		panic("[ERROR] Check project exist failed. Please check your parameters.")
	}

	return ToBool(result["isProjectExist"])
}

func createProject(IFconfig map[string]interface{}) {
	projectName := ToString(IFconfig["projectName"])
	projectType := ToString(IFconfig["projectType"])

	log.Output(1, fmt.Sprintf("[LOG]Creating the project named %s in the InsightFinder.", projectName))
	form := url.Values{}

	form.Add("operation", "create")
	form.Add("userName", ToString(IFconfig["userName"]))
	form.Add("licenseKey", ToString(IFconfig["licenseKey"]))
	form.Add("projectName", projectName)

	if IFconfig["systemName"] != nil {
		form.Add("systemName", ToString(IFconfig["systemName"]))
	} else {
		form.Add("systemName", projectName)
	}
	form.Add("instanceType", "PrivateCloud")
	form.Add("projectCloudType", "PrivateCloud")
	form.Add("dataType", ProjectTypeToDataType(projectType))
	form.Add("insightAgentType", ProjectTypeToAgentType(projectType, false))
	form.Add("samplingInterval", ToString(IFconfig["samplingInterval"]))
	form.Add("samplingIntervalInSeconds", ToString(IFconfig["samplingInterval"]))
	samplingIntervalINT, err := strconv.Atoi(ToString(IFconfig["samplingInterval"]))
	if err != nil {
		panic(err)
	}
	form.Add("samplingIntervalInSeconds", fmt.Sprint(samplingIntervalINT*60))
	headers := map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	}
	response, _ := SendRequest(
		http.MethodPost,
		FormCompleteURL(ToString(IFconfig["ifURL"]), PROJECT_END_POINT),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{},
	)
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	log.Output(1, ToString(result["message"]))
}
