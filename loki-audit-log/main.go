package main

import (
	"fmt"
	"log"
	"loki-audit-log/loki"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

const PROJECT_END_POINT = "api/v1/check-and-add-custom-project"
const IF_SECTION_NAME = "insightfinder"
const LOKI_SECTION_NAME = "loki"
const LOKI_REGEX = `com.insightfinder.models.AuditLog - User: ([^,]+), Operation: (.*)`

func getIFConfigsSection(p *configparser.ConfigParser) map[string]interface{} {
	// Required parameters
	var userName = ToString(GetConfigValue(p, IF_SECTION_NAME, "user_name", true))
	var licenseKey = ToString(GetConfigValue(p, IF_SECTION_NAME, "license_key", true))
	var projectName = ToString(GetConfigValue(p, IF_SECTION_NAME, "project_name", true))
	// We use uppercase for project log type.
	var projectType = strings.ToUpper(ToString(GetConfigValue(p, IF_SECTION_NAME, "project_type", true)))

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
	var instance_blacklist_string = ToString(GetConfigValue(p, IF_SECTION_NAME, "instance_blacklist", false))
	var timezone = ToString(GetConfigValue(p, IF_SECTION_NAME, "timezone_for_data", false))

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
		samplingIntervalInt, err := strconv.Atoi(samplingInterval)
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
	var instance_blacklist []string
	if len(instance_blacklist_string) > 0 {
		instance_blacklist = strings.Split(strings.TrimSpace(instance_blacklist_string), ",")
	} else {
		instance_blacklist = []string{}
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
		"ifURL":                     ifURL,
		"ifProxies":                 ifProxies,
		"isReplay":                  isReplay,
		"instance_blacklist":        instance_blacklist,
		"timezone":                  timezone,
	}
	return configIF
}

func getLokiConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var username = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "username", true))
	var password = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "password", true))
	var endpoint = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "endpoint", true))
	var query = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "query", true))
	// optional fields
	var startTime = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "startTime", false))
	var endTime = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "endTime", false))
	var maxEntriesLimitPerQuery = ToString(GetConfigValue(p, LOKI_SECTION_NAME, "maxEntriesLimitPerQuery", false))
	// ----------------- Process the configuration ------------------
	config := map[string]string{
		"username":                username,
		"password":                password,
		"endpoint":                endpoint,
		"query":                   query,
		"maxEntriesLimitPerQuery": maxEntriesLimitPerQuery,
		"startTime":               startTime,
		"endTime":                 endTime,
	}
	return config
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
		panic(err)
	}
	if len(allConfigs) == 0 {
		panic("[ERROR] No config file found in" + configPath)
	}
	return allConfigs
}

func getLokiAuditLog(p *configparser.ConfigParser) (res []loki.LokiLogData) {
	lokiConfig := getLokiConfig(p)
	lokiServer := loki.LokiServer{
		Username: lokiConfig["username"],
		Password: lokiConfig["password"],
		Endpoint: lokiConfig["endpoint"],
	}
	EndTime := time.Now()
	StartTime := EndTime.Add(-time.Minute)
	startTimeConfig := lokiConfig["startTime"]
	endTimeConfig := lokiConfig["endTime"]
	if startTimeConfig != "" {
		epochTimestamp := int64(ToInt(startTimeConfig))
		// Use time.Unix to convert the epoch timestamp (int) to a time.Time object
		StartTime = time.Unix(epochTimestamp, 0)
	}
	if endTimeConfig != "" {
		epochTimestamp := int64(ToInt(startTimeConfig))
		EndTime = time.Unix(epochTimestamp, 0)
	}
	if EndTime.Before(StartTime) {
		log.Output(1, "[WARNING] endTime is before startTime. Reset startTime to 1 minute before endTime")
		StartTime = EndTime.Add(-time.Minute * 20)
	}
	lokiServer.Initialize()
	interval := time.Minute * 20
	for t := StartTime; t.Before(EndTime); t = t.Add(interval) {
		fmt.Println("Current Time:", t)
		res = append(res, lokiServer.GetLogData(lokiConfig["query"], t, t.Add(interval))...)
	}
	return
}

func processLokiLog(p *configparser.ConfigParser, lokiData []loki.LokiLogData) (res []LogData) {
	operationRegex := regexp.MustCompile(LOKI_REGEX)
	for _, logEntry := range lokiData {
		operationMatch := operationRegex.FindStringSubmatch(logEntry.Text)

		if len(operationMatch) == 3 {
			user := operationMatch[1]
			operation := operationMatch[2]
			fmt.Printf("User: %s, Operation: %s\n", user, operation)
			res = append(res, LogData{
				Tag:       user,
				TimeStamp: logEntry.Timestamp.UnixMilli(),
				Data:      operation,
			})
		} else {
			log.Output(2, "[WARNING] No matched field found for currnet log record: "+logEntry.Text)
		}
	}
	return
}

func main() {
	allConfigs := getConfigFiles("")
	numOfConfigs := len(allConfigs)

	for i := 0; i < numOfConfigs; i++ {
		configPath := allConfigs[i]
		_ = log.Output(2, "Parsing the config file: "+configPath)
		p, err := configparser.NewConfigParserFromFile(configPath)
		if err != nil {
			log.Fatal(err)
			continue
		}
		lokiData := getLokiAuditLog(p)
		processedData := processLokiLog(p, lokiData)
		log.Output(1, "[INFO] Sucessfully processed log entries: "+fmt.Sprint(len(processedData)))
		IFconfig := getIFConfigsSection(p)
		println(IFconfig)
		sendLogData(processedData, IFconfig)
	}
	log.Output(1, "[LOG] All workers have finsihed. The agent will terminate by itself.")
}
