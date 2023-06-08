package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

const API_PREFIX = "/api/rest/"
const token_key = "DELL-EMC-TOKEN"

func getPStoreConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var userName = ToString(GetConfigValue(p, PowerStoreSectionName, "userName", true))
	var password = ToString(GetConfigValue(p, PowerStoreSectionName, "password", true))
	var metricPath = ToString(GetConfigValue(p, PowerStoreSectionName, "metricPath", true))
	var connectionUrl = ToString(GetConfigValue(p, PowerStoreSectionName, "connectionUrl", true))
	var instanceType = ToString(GetConfigValue(p, PowerStoreSectionName, "instanceType", true))
	var instanceNameField = ToString(GetConfigValue(p, PowerStoreSectionName, "instanceNameField", true))
	var timeStampField = ToString(GetConfigValue(p, PowerStoreSectionName, "timeStampField", true))
	// optional fields
	var metricWhitelist = ToString(GetConfigValue(p, PowerStoreSectionName, "metricWhitelist", false))

	var metric_interval_from_server = ToString(GetConfigValue(p, PowerStoreSectionName, "metric_interval_from_server", false))

	// ----------------- Process the configuration ------------------

	config := map[string]string{
		"userName":                    userName,
		"password":                    password,
		"metricPath":                  metricPath,
		"metricWhitelist":             metricWhitelist,
		"connectionUrl":               connectionUrl,
		"instanceType":                instanceType,
		"instanceNameField":           instanceNameField,
		"timeStampField":              timeStampField,
		"metric_interval_from_server": metric_interval_from_server,
	}
	return config
}

func getAuthToken(config map[string]string) (token string) {
	var headers map[string]string
	form := url.Values{}
	// We only need the header
	_, header := sendRequest(
		http.MethodGet,
		FormCompleteURL(config["connectionUrl"], API_PREFIX),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
	)
	log.Output(1, "[LOG] Getting token from endpoint")
	token = header.Get(token_key)
	if len(token) == 0 {
		panic("Can't get the token key. Please check your connection.")
	}
	return
}

func getPowerStoreInstanceList(config map[string]string) (objectList []string) {
	form := url.Values{}
	completeURL := FormCompleteURL(
		config["connectionUrl"], API_PREFIX,
	)
	headers := make(map[string]string, 0)
	headers[token_key] = config["token"]
	headers["Content-Type"] = "application/json"
	headers["Accept"] = "application/json"

	log.Output(1, "the token used in HTTP call: "+config["token"])
	res, _ := sendRequest(
		http.MethodGet,
		FormCompleteURL(
			completeURL, config["instanceType"],
		),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
	)

	var result []interface{}
	json.Unmarshal(res, &result)

	log.Output(1, "[LOG] Getting "+config["instanceType"])
	log.Output(1, string(res))
	log.Output(1, "[LOG] There are total "+fmt.Sprint(len(result))+" "+config["instanceType"])

	for _, x := range result {
		dict, ok := x.(map[string]interface{})
		if !ok {
			panic("[ERROR] Can't convert the result instance to map.")
		}
		log.Output(1, "[LOG] The id: "+ToString(dict["id"]))
		objectList = append(objectList, ToString(dict["id"]))
	}
	// Fake data
	// objectList = GetInstList()
	log.Output(1, "total objects returned "+fmt.Sprint(len(objectList)))
	return
}

func getPowerStoreMetricData(config map[string]string, objectId string, metricList []string, endpoint string) (result []interface{}) {
	headers := make(map[string]string, 0)
	headers[token_key] = config["token"]
	payload := PowerStoreMetricDataRequestPayload{
		Entity:    metricList[0],
		Entity_id: objectId,
		Interval:  config["metric_interval_from_server"],
	}
	jData, err := json.Marshal(payload)
	if err != nil {
		panic(err.Error())
	}
	completeURL := FormCompleteURL(
		config["connectionUrl"], API_PREFIX,
	)
	res, _ := sendRequest(
		http.MethodPost,
		FormCompleteURL(completeURL, endpoint),
		bytes.NewBuffer(jData),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
	)
	log.Output(1, "[LOG] Getting data from endpoint"+endpoint)
	log.Output(1, string(res))

	// The key is the instance name and the
	json.Unmarshal([]byte(res), &result)
	return
}

func PowerStoreDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	pStoreConfig := getPStoreConfig(p)
	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		InstanceDataMap: make(map[string]InstanceData),
	}

	pStoreConfig["token"] = getAuthToken(pStoreConfig)

	mapping, err := GetEndpointMetricMapping(pStoreConfig["metricPath"])
	if err != nil {
		panic(err)
	}
	var test int64
	println(test)
	ts := "2006-01-02T15:04:05Z"
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		fmt.Println(err)
	}
	fmt.Println(t.Unix())
	objectList := getPowerStoreInstanceList(pStoreConfig)
	// For powerStore, it should only have 1 endpoint
	for endpoint, metricList := range mapping {
		for _, object := range objectList {
			objectArray := getPowerStoreMetricData(pStoreConfig, object, metricList, endpoint)
			processArrayDataFromEndPoint(objectArray, pStoreConfig["timeStampField"], pStoreConfig["instanceNameField"], &data)
		}
	}
	return data
}
