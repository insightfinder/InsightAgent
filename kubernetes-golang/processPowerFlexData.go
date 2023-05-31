package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

var instanceTypeRegex = `{\$instanceType}`
var idRegex = `{\$id}`
var AUTHAPI = "/api/login"

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

func getInstanceList(config map[string]string) []string {
	form := url.Values{}
	getInstanceEndpoint := FormCompleteURL(
		config["connectionUrl"], config["idEndPoint"],
	)
	// TODO: Headers currently left empty
	var headers map[string]string
	log.Output(1, "the token used in instance HTTP call: "+config["token"])
	res := SendRequest(
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
	instanceList := make([]string, 0)

	log.Output(1, "[LOG] Getting instances")
	log.Output(1, string(res))
	log.Output(1, "[LOG] There are total "+fmt.Sprint(len(result))+" instances")

	for _, x := range result {
		dict, ok := x.(map[string]interface{})
		log.Output(1, "[LOG] The instance id: "+ToString(dict["id"]))
		if !ok {
			log.Fatal("[ERROR] Can't convert the result instance to map.")
		}
		instanceList = append(instanceList, ToString(dict["id"]))
	}
	// Fake data
	// instanceList := GetInstList()
	log.Output(1, "total instance returned "+fmt.Sprint(len(instanceList)))
	return instanceList
}

func formMetricDataPoint(metric string, value interface{}) MetricDataPoint {
	intVar, err := strconv.ParseFloat(ToString(value), 64)
	if err != nil {
		log.Fatal(err)
	}
	metricDP := MetricDataPoint{
		MetricName: metric,
		Value:      intVar,
	}
	return metricDP
}

func processDataFromInstances(instance string, config map[string]string, endpoint string, metrics []string, data *MetricDataReceivePayload) {
	IdRE := regexp.MustCompile(idRegex)
	InstanceRe := regexp.MustCompile(instanceTypeRegex)
	endpoint = string(IdRE.ReplaceAll([]byte(endpoint), []byte(instance)))
	endpoint = string(InstanceRe.ReplaceAll([]byte(endpoint), []byte(config["instanceType"])))
	var headers map[string]string
	form := url.Values{}
	res := SendRequest(
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

func parseData(data map[string]interface{}, timeStamp int64, metrics []string) DataInTimestamp {
	dataInTs := DataInTimestamp{
		TimeStamp:        timeStamp,
		MetricDataPoints: make([]MetricDataPoint, 0),
	}
	var stack Stack
	for _, metric := range metrics {
		metric = strings.ReplaceAll(metric, " ", "")
		stack.Push(MetricStack{
			Metric: data[metric],
			Prefix: metric,
		})
	}
	for {
		if stack.IsEmpty() {
			break
		}
		metricElem, _ := stack.Pop()
		curVal := metricElem.Metric
		curPrefix := metricElem.Prefix
		switch curVal.(type) {
		case string:
			dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, formMetricDataPoint(curPrefix, curVal))
		case float64, int64:
			dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, formMetricDataPoint(curPrefix, fmt.Sprint(curVal)))
		case interface{}:
			curMetricMap, success := curVal.(map[string]interface{})
			if !success {
				log.Fatal("[ERROR] Can't parse the metric " + curPrefix)
			}
			for k, v := range curMetricMap {
				stack.Push(MetricStack{
					Metric: v,
					Prefix: curPrefix + "." + k,
				})
			}
		default:
			log.Fatal("[ERROR] Wrong type input from the data")
		}
	}
	return dataInTs
}

func getToken(config map[string]string) string {
	authEndPoint := FormCompleteURL(
		config["connectionUrl"], AUTHAPI,
	)
	form := url.Values{}
	var headers map[string]string

	token := string(SendRequest(
		http.MethodGet,
		authEndPoint,
		strings.NewReader(form.Encode()),
		headers,
		AuthRequest{
			UserName: config["userName"],
			Password: config["password"],
		},
	))

	return token
}

func PowerFlexDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	config := getPFConfig(p)
	token := getToken(config)
	token = strings.ReplaceAll(token, "\"", "")
	log.Output(1, "[LOG] Successful get the token from Gateway API")
	log.Output(1, "[LOG] token: "+token)
	config["token"] = token
	instances := getInstanceList(config)

	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		InstanceDataMap: make(map[string]InstanceData),
	}

	endpointMapping, err := GetEndpointMetricMapping(config["metricPath"])
	if err != nil {
		log.Fatal(err)
	}
	for _, inst := range instances {
		log.Output(2, "[LOG] Getting data from instance: ["+inst+"] now.")
		for endpoint, metrics := range endpointMapping {
			processDataFromInstances(inst, config, endpoint, metrics, &data)
		}
	}
	return data
}
