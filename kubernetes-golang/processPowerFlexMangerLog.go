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
	"github.com/spacemonkeygo/openssl"
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

	config := map[string]string{
		"apiEndPoint":    apiEndPoint,
		"domain":         domain,
		"password":       password,
		"userName":       userName,
		"connectionUrl":  connectionUrl,
		"userAgent":      userAgent,
		"timeStampField": timeStampField,
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
	res, _ := SendRequest(
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
	requestStringList := []string{apiKey, http.MethodGet, config["apiEndPoint"], userAgent, timestamp}
	requestString := strings.Join(requestStringList, ":")

	hmac, err := openssl.NewHMAC([]byte(apiSecret), openssl.EVP_SHA256)
	if err != nil {
		log.Fatal(err)
	}
	hmac.Write([]byte(requestString))
	hashBytes, _ := hmac.Final()
	if err != nil {
		log.Fatal(err)
	}

	signature := base64.StdEncoding.EncodeToString(hashBytes)

	var resHeader map[string]string
	resHeader["x-dell-auth-key"] = apiKey
	resHeader["x-dell-auth-signature"] = signature
	resHeader["x-dell-auth-timestamp"] = timestamp
	resHeader["User-Agent"] = userAgent
	return resHeader
}

func getLogData(reqHeader map[string]string, config map[string]string) []interface{} {
	form := url.Values{}
	body, _ := SendRequest(
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

func processPFMLogData() {

}

func PowerFlexManagerDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) LogDataReceivePayload {
	config := getPFMConfig(p)
	authHeaders := authenticationPF(config)
	logData := getLogData(authHeaders, config)
	// projectName := ToString(IFconfig["projectName"])
	// userName := ToString(IFconfig["userName"])
	println(logData)
	return LogDataReceivePayload{}
}
