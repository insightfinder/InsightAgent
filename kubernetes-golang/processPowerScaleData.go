package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

func getPScaleConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var userName = ToString(GetConfigValue(p, PowerScaleSectionName, "userName", true))
	var password = ToString(GetConfigValue(p, PowerScaleSectionName, "password", true))
	var metricPath = ToString(GetConfigValue(p, PowerScaleSectionName, "metricPath", true))
	var connectionUrl = ToString(GetConfigValue(p, PowerScaleSectionName, "connectionUrl", true))
	var instanceNameField = ToString(GetConfigValue(p, PowerScaleSectionName, "instanceNameField", true))
	var timeStampField = ToString(GetConfigValue(p, PowerScaleSectionName, "timeStampField", true))
	// optional fields
	var metricWhitelist = ToString(GetConfigValue(p, PowerScaleSectionName, "metricWhitelist", false))

	// ----------------- Process the configuration ------------------

	config := map[string]string{
		"userName":          userName,
		"password":          password,
		"metricPath":        metricPath,
		"metricWhitelist":   metricWhitelist,
		"connectionUrl":     connectionUrl,
		"instanceNameField": instanceNameField,
		"timeStampField":    timeStampField,
	}
	return config
}

func getDataFromEndpoint(config map[string]string, endpoint string) map[string]interface{} {
	var headers map[string]string
	form := url.Values{}
	res := SendRequest(
		http.MethodGet,
		FormCompleteURL(config["connectionUrl"], endpoint),
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
	)
	log.Output(1, "[LOG] Getting data from endpoint"+endpoint)
	log.Output(1, string(res))

	// The key is the instance name and the
	var result map[string]interface{}
	json.Unmarshal([]byte(res), &result)
	return result
}

func processDataFromEndPoint(result map[string]interface{}, timeStampField string, instanceNameField string, metricList []string, data *MetricDataReceivePayload) {
	var objArrary []interface{}
	// For powerScale, there should only be 1 item in the metricList
	for _, metric := range metricList {
		objArrary = result[metric].([]interface{})
	}

	// // fake data
	// bytesData := GetFakeMetricData()
	// var result map[string]interface{}
	// json.Unmarshal(bytesData, &result)
	// objArrary := make([]interface{}, 1)
	// objArrary[0] = result
	// timeStamp := time.Now().UnixMilli()

	for index, obj := range objArrary {
		object, success := obj.(map[string]interface{})
		if !success {
			log.Fatal("[ERROR] Can't parse the object array with index: " + fmt.Sprint(index))
		}
		timeStamp := time.Unix(object[timeStampField].(int64), 0).UnixMilli()
		prasedData := ParseData(object, timeStamp, make([]string, 0))
		instance, success := object[instanceNameField].(string)
		if !success {
			log.Fatal("[ERROR] Failed to get instance name from the field: " + instanceNameField)
		}
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
}

func PowerScaleDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	psConfig := getPScaleConfig(p)
	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		InstanceDataMap: make(map[string]InstanceData),
	}

	mapping, err := GetEndpointMetricMapping(psConfig["metricPath"])
	if err != nil {
		log.Fatal(err)
	}
	for endpoint, metricList := range mapping {
		result := getDataFromEndpoint(psConfig, endpoint)
		processDataFromEndPoint(result, psConfig["timeStampField"], psConfig["instanceNameField"], metricList, &data)
	}
	return data
}
