package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
	"github.com/forgoer/openssl"
)

const FLEX_MANAGER_V3_Auth_API_PREFIX = "/Api/V1/Authenticate"
const InstanceType_API_Endpoint = "/Api/V1/Deployement"
const Depoyment_log_API_Endpoint = "/Api/V1/Deployment/asmdeployerogs/"

func getPFMConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var connectionUrl = ToString(GetConfigValue(p, PowerFlexManagerSection, "connectionUrl", true))
	var apiEndPoint = ToString(GetConfigValue(p, PowerFlexManagerSection, "apiEndPoint", true))
	var userAgent = ToString(GetConfigValue(p, PowerFlexManagerSection, "userAgent", true))
	var password = ToString(GetConfigValue(p, PowerFlexManagerSection, "password", true))
	var userName = ToString(GetConfigValue(p, PowerFlexManagerSection, "userName", true))
	var timeStampField = ToString(GetConfigValue(p, PowerFlexManagerSection, "timeStampField", true))
	var domain = ToString(GetConfigValue(p, PowerFlexManagerSection, "domain", true))
	var version = ToString(GetConfigValue(p, PowerFlexSectionName, "version", false))

	// ----------------- Process the configuration ------------------
	var instanceNameField = ToString(GetConfigValue(p, PowerFlexManagerSection, "instanceNameField", false))
	if version == "" {
		version = "4.0"
	}
	config := map[string]string{
		"apiEndPoint":       apiEndPoint,
		"domain":            domain,
		"password":          password,
		"userName":          userName,
		"connectionUrl":     connectionUrl,
		"userAgent":         userAgent,
		"timeStampField":    timeStampField,
		"instanceNameField": instanceNameField,
		"version":           version,
	}
	return config
}

func authenticationPF(config map[string]string) map[string]string {
	endPoint := FormCompleteURL(
		config["connectionUrl"], FLEX_MANAGER_V3_Auth_API_PREFIX,
	)
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	authRequest := FlexManagerAuthRequest{
		UserName: config["userName"],
		Password: config["password"],
		Domain:   config["domain"],
	}

	log.Output(2, "Authenticating to endpoint: "+endPoint)

	bytesPayload, _ := json.Marshal(authRequest)
	res, _ := sendRequest(
		http.MethodPost,
		endPoint,
		bytes.NewBuffer(bytesPayload),
		headers,
		AuthRequest{},
		true,
	)

	var result AuthResponse
	json.Unmarshal(res, &result)

	userAgent := config["userAgent"]
	apiKey := result.ApiKey
	apiSecret := result.ApiSecret
	timestamp := fmt.Sprint(time.Now().Unix())

	// Generate the signature using Hmac sha256
	requestStringList := []string{apiKey, http.MethodGet, config["apiEndPoint"], userAgent, timestamp}
	requestString := strings.Join(requestStringList, ":")
	hashBytes := openssl.HmacSha256(apiSecret, requestString)
	signature := base64.StdEncoding.EncodeToString(hashBytes)

	resHeader := make(map[string]string, 0)
	resHeader["x-dell-auth-key"] = apiKey
	resHeader["x-dell-auth-signature"] = signature
	resHeader["x-dell-auth-timestamp"] = timestamp
	resHeader["User-Agent"] = userAgent

	log.Output(2, "Authentication is done")
	return resHeader
}

func getPFMLogData(reqHeader map[string]string, config map[string]string, offset int, limit int) (result []map[string]interface{}) {
	params := url.Values{}
	//params.Add("sort", "-"+config["timeStampField"])
	params.Add("offset", fmt.Sprint(offset))
	params.Add("limit", fmt.Sprint(limit))
	endpoint := FormCompleteURL(config["connectionUrl"], config["apiEndPoint"]) + "?" + params.Encode()
	log.Output(2, "Getting log data from endpoint: "+endpoint)
	body, _ := sendRequest(
		http.MethodGet,
		endpoint,
		strings.NewReader(params.Encode()),
		reqHeader,
		AuthRequest{},
		true,
	)
	json.Unmarshal(body, &result)
	return
}

func getPFMLogData_V4(config map[string]string, instance string, offset int, limit int) (result []map[string]interface{}) {
	params := url.Values{}
	//params.Add("sort", "-"+config["timeStampField"])
	params.Add("offset", fmt.Sprint(offset))
	params.Add("limit", fmt.Sprint(limit))
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	// TODO: get Log data from instanceList
	headers["Authorization"] = "Bearer " + config["token"]
	endpoint := FormCompleteURL(config["connectionUrl"], Depoyment_log_API_Endpoint) + "?" + params.Encode()
	log.Output(2, "Getting log data from endpoint: "+endpoint)
	body, _ := sendRequest(
		http.MethodGet,
		endpoint,
		strings.NewReader(params.Encode()),
		headers,
		AuthRequest{},
		true,
	)
	json.Unmarshal(body, &result)
	return
}

func processPFMLogData(rawData []map[string]interface{}, config map[string]string) (processedData []LogData) {
	var instanceName string
	tsField := config["timeStampField"]
	instField := config["instanceNameField"]

	if len(instField) == 0 {
		log.Output(1, "No instance field value is found. Will use default instance name.")
		instanceName = "NO_INSTANCE_NAME"
	}

	for _, logObj := range rawData {

		ts, err := time.Parse(time.RFC3339, logObj[tsField].(string))
		if err != nil {
			log.Output(2, "Error parsing timestamp: "+fmt.Sprint(logObj[tsField]))
			continue
		}

		if len(instField) != 0 {
			instanceName = logObj[instField].(string)
		}

		processedData = append(processedData, LogData{
			TimeStamp: ts.UnixMilli(),
			Tag:       instanceName,
			Data:      logObj,
		})
	}

	log.Output(2, "Log data processing is done with entries:"+fmt.Sprint(len(processedData)))
	return
}

func getPowerFlexManagerDeploymentInstanceList_V4(config map[string]string) (instanceList []string) {
	form := url.Values{}
	getInstanceEndpoint := FormCompleteURL(
		config["connectionUrl"], InstanceType_API_Endpoint,
	)
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	headers["Authorization"] = "Bearer " + config["token"]
	res, _ := sendRequest(
		http.MethodGet,
		getInstanceEndpoint,
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{},
		true,
	)

	var result []interface{}
	json.Unmarshal(res, &result)

	log.Output(1, "[LOG] Getting instances")
	log.Output(1, "[LOG] There are total "+fmt.Sprint(len(result))+" instances")

	for _, x := range result {
		dict, ok := x.(map[string]interface{})
		log.Output(1, "[LOG] The instance id: "+ToString(dict["id"]))
		if !ok {
			log.Output(2, "[ERROR] Can't convert the result instance to map.")
		}
		instanceList = append(instanceList, ToString(dict["id"]))
	}
	log.Output(1, "total instance returned "+fmt.Sprint(len(instanceList)))
	return
}

func PowerFlexManagerDataStream(cfg map[string]string, offset int, limit int) []LogData {
	var rawLogData []map[string]interface{}
	if cfg["version"] == "" || cfg["version"] == "3.0" {
		authHeaders := authenticationPF(cfg)
		rawLogData = getPFMLogData(authHeaders, cfg, offset, limit)
		log.Output(1, "The number of log entries being processed is: "+fmt.Sprint(len(rawLogData)))
		return processPFMLogData(rawLogData, cfg)
	}
	res := []LogData{}
	token := getPowerflexToken_V4(cfg)
	if token == "" {
		log.Output(2, "[ERROR]Can't get token for powerflex manager from "+cfg["connectionUrl"])
	}
	log.Output(1, "[LOG] Successful get the token from Gateway API")
	cfg["token"] = token
	instanceList := getPowerFlexManagerDeploymentInstanceList_V4(cfg)
	for i := 0; i < len(instanceList); i++ {
		rawLogData = getPFMLogData_V4(cfg, instanceList[i], offset, limit)
		res = append(res, processPFMLogData(rawLogData, cfg)...)
	}
	log.Output(1, "The number of log entries being processed is: "+fmt.Sprint(len(res)))
	return res
}
