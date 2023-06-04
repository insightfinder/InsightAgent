package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
	"github.com/forgoer/openssl"
)

func getPFMConfig(p *configparser.ConfigParser) map[string]string {
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
	config := map[string]string{
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

func authenticationPF(config map[string]string) map[string]string {
	endPoint := FormCompleteURL(
		config["connectionUrl"], AUTHAPI,
	)
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	authRequest := AuthRequest{
		UserName: config["userName"],
		Password: config["password"],
	}
	bytesPayload, _ := json.Marshal(authRequest)
	res, _ := sendRequest(
		http.MethodPost,
		FormCompleteURL(config["connectionUrl"], endPoint),
		bytes.NewBuffer(bytesPayload),
		headers,
		AuthRequest{},
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
	return resHeader
}

func getPFMLogData(reqHeader map[string]string, config map[string]string) []interface{} {
	form := url.Values{}
	body, _ := sendRequest(
		http.MethodGet,
		FormCompleteURL(config["connectionUrl"], config["apiEndPoint"]),
		strings.NewReader(form.Encode()),
		reqHeader,
		AuthRequest{},
	)
	var result []interface{}
	json.Unmarshal(body, &result)
	return result
}

func processPFMLogData(rawData []interface{}, config map[string]string) []LogData {
	processedData := make([]LogData, 0)
	var instanceName string
	tsField := config["timeStampField"]
	instField := config["instanceNameField"]
	if len(instField) == 0 {
		log.Output(1, "No instance field value is found. Will use default instance name.")
		instanceName = "NO_INSTANCE_NAME"
	}
	for _, dp := range rawData {
		logObj, success := dp.(map[string]string)
		if !success {
			panic("Can't cast log object to map[string]string. Please check your log input.")
		}

		ts, err := strconv.ParseInt(logObj[tsField], 10, 64)
		if err != nil {
			panic(err.Error())
		}

		if len(instField) != 0 {
			instanceName = logObj[instField]
		}

		processedData = append(processedData, LogData{
			TimeStamp: ts,
			Tag:       instanceName,
			Data:      logObj,
		})
	}
	return processedData
}

func PowerFlexManagerDataStream(p *configparser.ConfigParser) []LogData {
	config := getPFMConfig(p)
	authHeaders := authenticationPF(config)
	logData := getPFMLogData(authHeaders, config)
	log.Output(1, "The number of log entires being proccessed is: "+fmt.Sprint(len(logData)))
	return processPFMLogData(logData, config)
}
