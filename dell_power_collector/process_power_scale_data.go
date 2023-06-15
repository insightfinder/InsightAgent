package main

import (
	"encoding/json"
	"log"
	"net/http"
	"net/url"
	"strings"

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
	var firstLayerkey = ToString(GetConfigValue(p, PowerScaleSectionName, "firstLayerkey", true))
	// optional fields

	// ----------------- Process the configuration ------------------

	config := map[string]string{
		"userName":          userName,
		"password":          password,
		"metricPath":        metricPath,
		"connectionUrl":     connectionUrl,
		"instanceNameField": instanceNameField,
		"timeStampField":    timeStampField,
		"firstLayerkey":     firstLayerkey,
	}
	return config
}

func getDataFromEndpoint(config map[string]string, endpoint string) (result map[string]interface{}) {
	var headers map[string]string
	form := url.Values{}
	res, _ := sendRequest(
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
	json.Unmarshal([]byte(res), &result)
	return
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

	connectionUrl := psConfig["connectionUrl"]
	connectionUrlList := []string{connectionUrl}

	if strings.Contains(connectionUrl, ",") {
		connectionUrlList = strings.Split(connectionUrl, ",")
	}

	for _, connUrl := range connectionUrlList {
		config := copyMap(psConfig)
		config["connectionUrl"] = connUrl
		mapping, err := GetEndpointMetricMapping(config["metricPath"])
		if err != nil {
			panic(err)
		}
		for endpoint, metricList := range mapping {
			result := getDataFromEndpoint(config, endpoint)

			firstLayerKey := config["firstLayerkey"]
			objArray, ok := result[firstLayerKey].([]interface{})
			if !ok {
				panic("Can't cast the result object to array of interface for PowerScale metric. Please check your firstLayerKey.")
			}
			processArrayDataFromEndPoint(objArray, metricList, config["timeStampField"], "Epoch", config["instanceNameField"], &data)
		}
	}

	return data
}
