package main

import (
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

	// ----------------- Process the configuration ------------------

	re := regexp.MustCompile(instanceTypeRegex)
	idEndPoint = string(re.ReplaceAll([]byte(idEndPoint), []byte(instanceType)))

	config := map[string]string{
		"userName":        userName,
		"password":        password,
		"instanceType":    instanceType,
		"metricPath":      metricPath,
		"metricWhitelist": metricWhitelist,
		"idEndPoint":      idEndPoint,
		"connectionUrl":   connectionUrl,
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

func processDataFromInstances(instance string, config map[string]string, endpoint string, metrics []string, data *MetricDataReceivePayload) {
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
	)

	log.Output(1, "[LOG] Getting instances data")
	log.Output(1, string(res))

	timeStamp := time.Now().UnixMilli()

	// Fake data for testing
	// res := GetFakeMetricData()
	var result map[string]interface{}
	json.Unmarshal([]byte(res), &result)
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

func getToken(config map[string]string) string {
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
	)

	return string(token)
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
		cfg["connectionUrl"] = connUrl

		token := getToken(cfg)
		token = strings.ReplaceAll(token, "\"", "")
		log.Output(1, "[LOG] Successful get the token from Gateway API")
		log.Output(1, "[LOG] token: "+token)
		cfg["token"] = token
		instances := getInstanceList(cfg)

		endpointMapping, err := GetEndpointMetricMapping(cfg["metricPath"])
		if err != nil {
			panic(err)
		}
		for _, inst := range instances {
			log.Output(2, "[LOG] Getting data from instance: ["+inst+"] now.")
			for endpoint, metrics := range endpointMapping {
				processDataFromInstances(inst, cfg, endpoint, metrics, &data)
			}
		}
	}

	return data
}
