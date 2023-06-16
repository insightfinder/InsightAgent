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

const FLEX_MANAGER_API_PREFIX = "/Api/V1/Authenticate"

func getPFMConfig(p *configparser.ConfigParser) map[string]interface{} {
	// required fields
	var connectionUrl = ToString(GetConfigValue(p, PowerFlexManagerSection, "connectionUrl", true))
	var apiEndPoint = ToString(GetConfigValue(p, PowerFlexManagerSection, "apiEndPoint", true))
	var userAgent = ToString(GetConfigValue(p, PowerFlexManagerSection, "userAgent", true))
	var password = ToString(GetConfigValue(p, PowerFlexManagerSection, "password", true))
	var userName = ToString(GetConfigValue(p, PowerFlexManagerSection, "userName", true))
	var timeStampField = ToString(GetConfigValue(p, PowerFlexManagerSection, "timeStampField", true))
	var domain = ToString(GetConfigValue(p, PowerFlexManagerSection, "domain", true))

	// ----------------- Process the configuration ------------------
	var instanceNameField = ToString(GetConfigValue(p, PowerFlexManagerSection, "instanceNameField", false))
	config := map[string]interface{}{
		"apiEndPoint":       apiEndPoint,
		"domain":            domain,
		"password":          password,
		"userName":          userName,
		"connectionUrl":     connectionUrl,
		"userAgent":         userAgent,
		"timeStampField":    timeStampField,
		"instanceNameField": instanceNameField,
	}
	return config
}

func authenticationPF(config map[string]interface{}) map[string]string {
	endPoint := FormCompleteURL(
		config["connectionUrl"].(string), FLEX_MANAGER_API_PREFIX,
	)
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	authRequest := FlexManagerAuthRequest{
		UserName: config["userName"].(string),
		Password: config["password"].(string),
		Domain:   config["domain"].(string),
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

	userAgent := config["userAgent"].(string)
	apiKey := result.ApiKey
	apiSecret := result.ApiSecret
	timestamp := fmt.Sprint(time.Now().Unix())

	// Generate the signature using Hmac sha256
	requestStringList := []string{apiKey, http.MethodGet, config["apiEndPoint"].(string), userAgent, timestamp}
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

func getPFMLogData(reqHeader map[string]string, config map[string]interface{}, offset int) (result []map[string]interface{}) {
	params := url.Values{}
	//params.Add("sort", "-"+config["timeStampField"])
	params.Add("offset", fmt.Sprint(offset))
	params.Add("limit", "1000")
	endpoint := FormCompleteURL(config["connectionUrl"].(string), config["apiEndPoint"].(string)) + "?" + params.Encode()
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

func processPFMLogData(rawData []map[string]interface{}, config map[string]interface{}) (processedData []LogData) {
	var instanceName string
	tsField := config["timeStampField"].(string)
	instField := config["instanceNameField"].(string)

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

func PowerFlexManagerDataStream(config map[string]interface{}, offset int) []LogData {
	authHeaders := authenticationPF(config)
	rawLogData := getPFMLogData(authHeaders, config, offset)

	log.Output(1, "The number of log entries being processed is: "+fmt.Sprint(len(rawLogData)))
	return processPFMLogData(rawLogData, config)
}
