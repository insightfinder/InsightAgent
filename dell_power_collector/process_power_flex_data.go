package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

const instanceTypeRegex = `{\$instanceType}`
const idRegex = `{\$id}`
const AUTHAPI = "/api/login"
const AUTHAPI_V4 = "/rest/auth/login"

func getPFConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var userName = ToString(GetConfigValue(p, PowerFlexSectionName, "userName", true))
	var password = ToString(GetConfigValue(p, PowerFlexSectionName, "password", true))
	var instanceType = ToString(GetConfigValue(p, PowerFlexSectionName, "instanceType", true))
	var metricPath = ToString(GetConfigValue(p, PowerFlexSectionName, "metricPath", true))
	var idEndPoint = ToString(GetConfigValue(p, PowerFlexSectionName, "idEndPoint", true))
	var connectionUrl = ToString(GetConfigValue(p, PowerFlexSectionName, "connectionUrl", true))
	// optional fields
	var metricWhitelist = ToString(GetConfigValue(p, PowerFlexSectionName, "metricWhitelist", false))
	var version = ToString(GetConfigValue(p, PowerFlexSectionName, "version", false))

	// ----------------- Process the configuration ------------------

	re := regexp.MustCompile(instanceTypeRegex)
	idEndPoint = string(re.ReplaceAll([]byte(idEndPoint), []byte(instanceType)))
	if version == "" {
		version = "4.0"
	}

	config := map[string]string{
		"userName":        userName,
		"password":        password,
		"instanceType":    instanceType,
		"metricPath":      metricPath,
		"metricWhitelist": metricWhitelist,
		"idEndPoint":      idEndPoint,
		"connectionUrl":   connectionUrl,
		"version":         version,
	}
	return config
}

func getInstanceList(config map[string]string) (instanceList []string) {
	form := url.Values{}
	getInstanceEndpoint := FormCompleteURL(
		config["connectionUrl"], config["idEndPoint"],
	)
	// TODO: Headers currently left empty
	var headers map[string]string
	log.Output(1, "the token used in instance HTTP call: "+config["token"])
	res, _ := sendRequest(
		http.MethodGet,
		getInstanceEndpoint,
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: "",
			Password: config["token"],
		},
		true,
	)

	var result []interface{}
	json.Unmarshal(res, &result)

	log.Output(1, "[LOG] Getting instances")
	log.Output(1, string(res))
	log.Output(1, "[LOG] There are total "+fmt.Sprint(len(result))+" instances")

	for _, x := range result {
		dict, ok := x.(map[string]interface{})
		log.Output(1, "[LOG] The instance id: "+ToString(dict["id"]))
		if !ok {
			panic("[ERROR] Can't convert the result instance to map.")
		}
		instanceList = append(instanceList, ToString(dict["id"]))
	}
	// Fake data
	// instanceList = GetInstList()
	log.Output(1, "total instance returned "+fmt.Sprint(len(instanceList)))
	return
}

func getInstanceList_V4(config map[string]string) (instanceList []string) {
	form := url.Values{}
	getInstanceEndpoint := FormCompleteURL(
		config["connectionUrl"], config["idEndPoint"],
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

func getDataFromInstances(instance string, config map[string]string, endpoint string) map[string]interface{} {
	IdRE := regexp.MustCompile(idRegex)
	InstanceRe := regexp.MustCompile(instanceTypeRegex)
	endpoint = string(IdRE.ReplaceAll([]byte(endpoint), []byte(instance)))
	endpoint = string(InstanceRe.ReplaceAll([]byte(endpoint), []byte(config["instanceType"])))
	var headers map[string]string
	form := url.Values{}
	res, _ := sendRequest(
		http.MethodGet,
		FormCompleteURL(config["connectionUrl"], endpoint),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: "",
			Password: config["token"],
		},
		true,
	)

	log.Output(1, "[LOG] Getting instances data")
	log.Output(1, "[LOG] Data counts from server: "+string(res))

	// Fake data for testing
	// res := GetFakeMetricData()
	var result map[string]interface{}
	json.Unmarshal([]byte(res), &result)
	return result
}

func getDataFromInstances_V4(instance string, config map[string]string, endpoint string) map[string]interface{} {
	IdRE := regexp.MustCompile(idRegex)
	InstanceRe := regexp.MustCompile(instanceTypeRegex)
	endpoint = string(IdRE.ReplaceAll([]byte(endpoint), []byte(instance)))
	endpoint = string(InstanceRe.ReplaceAll([]byte(endpoint), []byte(config["instanceType"])))
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	headers["Authorization"] = "Bearer " + config["token"]
	form := url.Values{}
	res, _ := sendRequest(
		http.MethodGet,
		FormCompleteURL(config["connectionUrl"], endpoint),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{},
		true,
	)

	log.Output(1, "[LOG] Getting instances data")

	var result map[string]interface{}
	json.Unmarshal([]byte(res), &result)

	log.Output(1, "[LOG] Data counts from server: "+fmt.Sprint(len(result)))
	return result
}

func processPowerFlexData(instance string, result map[string]interface{}, metrics []string, data *MetricDataReceivePayload) {
	timeStamp := time.Now().UnixMilli()
	prasedData := parseData(result, timeStamp, metrics)

	instanceData, ok := data.InstanceDataMap[instance]
	if !ok {
		// Current Instance didn't exist
		instanceData = InstanceData{
			InstanceName:       instance,
			ComponentName:      instance,
			DataInTimestampMap: make(map[int64]DataInTimestamp),
		}
		data.InstanceDataMap[instance] = instanceData
	}
	instanceData.DataInTimestampMap[timeStamp] = prasedData
}

func getToken_V3(config map[string]string) string {
	authEndPoint := FormCompleteURL(
		config["connectionUrl"], AUTHAPI,
	)
	form := url.Values{}
	var headers map[string]string

	token, _ := sendRequest(
		http.MethodGet,
		authEndPoint,
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
		true,
	)

	return string(token)
}

func getPowerflexToken_V4(config map[string]string) string {
	authEndPoint := FormCompleteURL(
		config["connectionUrl"], AUTHAPI_V4,
	)
	log.Output(1, "URL: "+authEndPoint)

	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}

	authData, err := json.Marshal(map[string]interface{}{
		"username": config["userName"],
		"password": config["password"],
	})
	if err != nil {
		fmt.Println("Error:", err)
		return ""
	}

	token, _ := sendRequest(
		http.MethodPost,
		authEndPoint,
		bytes.NewBuffer(authData),
		headers,
		AuthRequest{},
		true,
	)
	var res map[string]string
	json.Unmarshal(token, &res)
	return res["access_token"]
}

func PowerFlexDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		InstanceDataMap: make(map[string]InstanceData),
	}

	config := getPFConfig(p)

	connectionUrl := config["connectionUrl"]
	connectionUrlList := []string{connectionUrl}

	if strings.Contains(connectionUrl, ",") {
		connectionUrlList = strings.Split(connectionUrl, ",")
	}

	for _, connUrl := range connectionUrlList {
		cfg := copyMap(config)
		cfg["connectionUrl"] = strings.TrimSpace(connUrl)
		if cfg["version"] == "" || cfg["version"] == "3.0" {
			log.Output(1, "[LOG] Get Version 3.0 powerflex data")
			token := getToken_V3(cfg)
			token = strings.ReplaceAll(token, "\"", "")
			log.Output(1, "[LOG] Get the token from Gateway API: "+token)
			if token == "" {
				log.Output(1, "[ERROR] No token can be retrieved. Skip this host: "+connUrl)
				continue
			}
			cfg["token"] = token
			instances := getInstanceList(cfg)

			endpointMapping, err := GetEndpointMetricMapping(cfg["metricPath"])
			if err != nil {
				log.Output(2, err.Error())
				continue
			}
			for _, inst := range instances {
				log.Output(2, "[LOG] Getting data from instance: ["+inst+"] now.")
				for endpoint, metrics := range endpointMapping {
					processPowerFlexData(inst, getDataFromInstances(inst, cfg, endpoint), metrics, &data)
				}
			}
		} else if cfg["version"] == "4.0" {
			log.Output(1, "[LOG] Get Version 4.0 powerflex data")
			token := getPowerflexToken_V4(cfg)
			if token == "" {
				log.Output(1, "[Warning] No token can be retrieved. Skip this host: "+connUrl)
				continue
			}
			token = strings.ReplaceAll(token, "\"", "")
			log.Output(1, "[LOG] Successful get the token from Gateway API")

			cfg["token"] = token
			instances := getInstanceList_V4(cfg)

			endpointMapping, err := GetEndpointMetricMapping(cfg["metricPath"])
			if err != nil {
				log.Output(2, err.Error())
				continue
			}
			for _, inst := range instances {
				log.Output(2, "[LOG] Getting data from instance: ["+inst+"] now.")
				for endpoint, metrics := range endpointMapping {
					processPowerFlexData(inst, getDataFromInstances_V4(inst, cfg, endpoint), metrics, &data)
				}
			}
		}
	}
	return data
}
