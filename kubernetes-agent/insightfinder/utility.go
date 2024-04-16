package insightfinder

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"github.com/carlmjohnson/requests"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"time"
)

const DEFAULT_MATADATE_MAX_INSTANCE = 1500
const PROJECT_END_POINT = "api/v1/check-and-add-custom-project"
const IF_SECTION_NAME = "insightfinder"

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	curdir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	mydir, err := filepath.Abs(curdir)
	if err != nil {
		panic(err)
	}
	return filepath.Join(mydir, filename)
}

// The path of the configuration files. If input is empty string,
// it will read from ./conf.d
func GetConfigFiles(configRelativePath string) []string {
	if configRelativePath == "" {
		// default value for configuration path
		configRelativePath = "conf.d"
	}
	configPath := AbsFilePath(configRelativePath)
	slog.Info("Reading config files from directory: " + configPath)
	allConfigs, err := filepath.Glob(configPath + "/*.ini")
	if err != nil {
		panic(err)
	}
	if len(allConfigs) == 0 {
		panic("[ERROR] No config file found in" + configPath)
	}
	return allConfigs
}

func GetConfigValue(p *configparser.ConfigParser, section string, param string, required bool) interface{} {
	result, err := p.Get(section, param)
	if err != nil && required {
		panic(err)
	}
	if result == "" && required {
		panic("[ERROR] InsightFinder configuration [" + param + "] is required!")
	}
	return result
}

func FormCompleteURL(link string, endpoint string) string {
	postUrl, err := url.Parse(link)
	if err != nil {
		slog.Error("[ERROR] Fail to pares the URL. Please check your config.")
		panic(err)
	}
	postUrl.Path = path.Join(postUrl.Path, endpoint)
	return postUrl.String()
}

func ToString(inputVar interface{}) string {
	if inputVar == nil {
		return ""
	}
	return fmt.Sprint(inputVar)
}

func ToBool(inputVar interface{}) (boolValue bool) {
	if inputVar == nil || inputVar == "" {
		return false
	}
	switch castedVal := inputVar.(type) {
	case string:
		var err error
		boolValue, err = strconv.ParseBool(castedVal)
		if err != nil {
			panic("[ERROR] Wrong input type. Can not convert current input to boolean.")
		}
	case bool:
		boolValue = castedVal
	}
	return boolValue
}

func ToInt(inputVar interface{}) int {
	if inputVar == nil {
		return 0
	}
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "int" {
		return inputVar.(int)
	}
	panic("[ERROR] Wrong input type. Can not convert current input to int.")
}

// Need to test the functionality. Only support primitive type.
func Contains(s []interface{}, str interface{}) bool {
	for _, v := range s {
		if v == str {
			return true
		}
	}
	return false
}

// ------------------ Project Type transformation ------------------------

func ProjectTypeToAgentType(projectType string, isReplay bool, isContainer bool) string {
	if isReplay {
		if strings.Contains(projectType, "METRIC") {
			return "MetricFile"
		} else {
			return "LogFile"
		}
	}
	if isContainer {
		if strings.Contains(projectType, "METRIC") {
			return "containerStreaming"
		} else {
			return "ContainerCustom"
		}

	}

	return "Custom"

}

func IsValidProjectType(projectType string) bool {
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

func ProjectTypeToDataType(projectType string) string {
	switch projectType {
	case "METRIC":
		return "Metric"
	case "METRICREPLAY":
		return "Metric"
	case "ALERT":
		return "Alert"
	case "INCIDENT":
		return "Incident"
	case "DEPLOYMENT":
		return "Deployment"
	case "TRACE":
		return "Trace"
	default:
		return "Log"
	}
}

func GetInsightFinderConfig(p *configparser.ConfigParser) map[string]interface{} {
	// Required parameters
	var userName = ToString(GetConfigValue(p, IF_SECTION_NAME, "user_name", true))
	var licenseKey = ToString(GetConfigValue(p, IF_SECTION_NAME, "license_key", true))
	var projectName = ToString(GetConfigValue(p, IF_SECTION_NAME, "project_name", true))
	var cloudType = ToString(GetConfigValue(p, IF_SECTION_NAME, "cloud_type", true))
	// We use uppercase for project log type.
	var projectType = strings.ToUpper(ToString(GetConfigValue(p, IF_SECTION_NAME, "project_type", true)))
	var isContainer = ToBool(GetConfigValue(p, IF_SECTION_NAME, "is_container", true))
	var runInterval = ToString(GetConfigValue(p, IF_SECTION_NAME, "run_interval", false))
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
			slog.Error(err.Error())
			slog.Error("[ERROR] Meta data max instance can only be integer number.")
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
		"isContainer":               isContainer,
		"cloudType":                 cloudType,
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
			slog.Warn(fmt.Sprintf("Didn't find the project named %s. Start creating project in the InsightFinder.", projectName))
			createProject(IFconfig)
			slog.Info("Sleep for 5 seconds to wait for project creation and will check the project exisitense again.")
			time.Sleep(time.Second * 5)
			if !isProjectExist(IFconfig) {
				panic("[ERROR] Fail to create project " + projectName)
			}
			slog.Info(fmt.Sprintf("Create project %s successfully!", projectName))
		} else {
			slog.Info(fmt.Sprintf("Project named %s exist. Program will continue.", projectName))
		}
	}
}

func isProjectExist(IFconfig map[string]interface{}) bool {
	projectName := ToString(IFconfig["projectName"])
	slog.Info(fmt.Sprintf("Check if the project named %s exists in the InsightFinder.", projectName))
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
		slog.Error("[ERROR] Check project exist failed. Please check your parameters.")
	}

	return ToBool(result["isProjectExist"])
}

func createProject(IFconfig map[string]interface{}) {

	var requestBody ProjectCreationModel
	var requestForm = make(url.Values)
	isContainer := ToBool(IFconfig["isContainer"])
	projectType := ToString(IFconfig["projectType"])

	// Add data to body
	requestBody.ProjectName = ToString(IFconfig["projectName"])
	requestBody.Operation = "create"
	requestBody.UserName = ToString(IFconfig["userName"])
	requestBody.LicenseKey = ToString(IFconfig["licenseKey"])
	requestBody.InstanceType = "PrivateCloud"
	requestBody.DataType = ProjectTypeToDataType(projectType)
	requestBody.InsightAgentType = ProjectTypeToAgentType(ToString(IFconfig["projectType"]), false, isContainer)
	samplingInterval, _ := strconv.Atoi(ToString(IFconfig["samplingInterval"]))
	requestBody.SamplingInterval = samplingInterval
	requestBody.SamplingIntervalInSeconds = samplingInterval * 60

	if IFconfig["systemName"] != nil {
		requestBody.SystemName = ToString(IFconfig["systemName"])
	} else {
		requestBody.SystemName = requestBody.ProjectName
	}
	requestForm.Add("systemName", requestBody.SystemName)

	// Add default values for CloudType
	if IFconfig["cloudType"] != nil {
		requestBody.ProjectCloudType = ToString(IFconfig["cloudType"])
	} else {
		requestBody.ProjectCloudType = "PrivateCloud"
	}

	// Add data to form
	requestForm.Add("operation", "create")
	requestForm.Add("samplingInterval", ToString(requestBody.SamplingInterval))
	requestForm.Add("userName", requestBody.UserName)
	requestForm.Add("projectName", requestBody.ProjectName)
	requestForm.Add("licenseKey", requestBody.LicenseKey)
	requestForm.Add("instanceType", requestBody.InstanceType)
	requestForm.Add("samplingIntervalInSeconds", ToString(requestBody.SamplingIntervalInSeconds))
	requestForm.Add("dataType", requestBody.DataType)
	requestForm.Add("insightAgentType", requestBody.InsightAgentType)
	requestForm.Add("projectCloudType", requestBody.ProjectCloudType)
	requestForm.Add("systemName", requestBody.SystemName)

	slog.Info(fmt.Sprintf("[LOG]Creating the project named %s in the InsightFinder.", requestBody.ProjectName))

	//var result ProjectCheckModel
	var resultStr string
	err := requests.URL(FormCompleteURL(ToString(IFconfig["ifURL"]), PROJECT_END_POINT)).Header("agent-type", "Stream").BodyJSON(requestBody).Params(requestForm).ToString(&resultStr).Fetch(context.Background())
	if err != nil {
		fmt.Println(err)
	}
}
