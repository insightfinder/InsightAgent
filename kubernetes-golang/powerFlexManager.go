package main

import (
	"bytes"
	"encoding/json"
	"net/http"

	"github.com/bigkevmcd/go-configparser"
)

var powerFlexManagerSection = "powerFlexManager"

func getPFMConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var connectionUrl = ToString(GetConfigValue(p, powerFlexManagerSection, "connectionUrl", true))
	var apiEndPoint = ToString(GetConfigValue(p, powerFlexManagerSection, "apiEndPoint", true))
	var domain = ToString(GetConfigValue(p, powerFlexManagerSection, "domain", true))
	var password = ToString(GetConfigValue(p, powerFlexManagerSection, "idEndPoint", true))
	var userName = ToString(GetConfigValue(p, powerFlexManagerSection, "userName", true))

	// ----------------- Process the configuration ------------------

	config := map[string]string{
		"apiEndPoint":   apiEndPoint,
		"domain":        domain,
		"password":      password,
		"userName":      userName,
		"connectionUrl": connectionUrl,
	}
	return config
}

func authenticationPF(config map[string]string) {
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
	res := SendRequest(
		http.MethodPost,
		FormCompleteURL(config["connectionUrl"], endPoint),
		bytes.NewBuffer(bytesPayload),
		headers,
		AuthRequest{},
	)
	var result AuthResponse
	json.Unmarshal(res, &result)
	// userAgent := "curl/7.64.1"
	// apiKey := result.ApiKey
	// apiSecret := result.ApiSecret
	// timestamp := fmt.Sprint(time.Now().UnixMilli())
	// requestStringList := []string{apiKey, http.MethodGet, config["apiEndPoint"], userAgent, timestamp}
	// requestString := strings.Join(requestStringList, ":")

	// // hmac, err := openssl.NewHMAC([]byte(apiSecret), openssl.EVP_SHA256)
	// if err != nil {
	// 	log.Fatal(err)
	// }
	// hmac.Write([]byte(requestString))
	// hashBytes, _ := hmac.Final()
	// if err != nil {
	// 	log.Fatal(err)
	// }

	// signature := base64.StdEncoding.EncodeToString(hashBytes)
	// var resHeader map[string]string
	// resHeader["x-dell-auth-key"] = apiKey
	// resHeader["x-dell-auth-signature"] = signature
	// resHeader["x-dell-auth-timestamp"] = timestamp
	// resHeader["User-Agent"] = userAgent
	// return resHeader
}

func getLogData(reqHeader map[string]string, config map[string]string) {
	// form := url.Values{}
	// res := SendRequest(
	// 	http.MethodGet,
	// 	FormCompleteURL(config["connectionUrl"], config["apiEndPoint"]),
	// 	strings.NewReader(form.Encode()),
	// 	reqHeader,
	// )

}

func PowerFlexManagerDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) {
	// config := getPFMConfig(p)
	// authHeaders := authenticationPF(config)
	// // logData := getLogData(authHeaders, config)
	// projectName := ToString(IFconfig["projectName"])
	// userName := ToString(IFconfig["userName"])
	// data := MetricDataReceivePayload{
	// 	ProjectName:     projectName,
	// 	UserName:        userName,
	// 	InstanceDataMap: make(map[string]InstanceData),
	// }

}
