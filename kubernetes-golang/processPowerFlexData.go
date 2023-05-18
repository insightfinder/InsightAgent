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

var powerFlexSectionName = "powerFlex"
var instanceTypeRegex = `{\$instanceType}`
var idRegex = `{\$id}`
var AUTHAPI = "/api/login"

func getPFConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var userName = ToString(GetConfigValue(p, powerFlexSectionName, "userName", true))
	var password = ToString(GetConfigValue(p, powerFlexSectionName, "password", true))
	var instanceType = ToString(GetConfigValue(p, powerFlexSectionName, "instanceType", true))
	var metricPath = ToString(GetConfigValue(p, powerFlexSectionName, "metricPath", true))
	var dataEndPoint = ToString(GetConfigValue(p, powerFlexSectionName, "dataEndPoint", true))
	var idEndPoint = ToString(GetConfigValue(p, powerFlexSectionName, "idEndPoint", true))
	var connectionUrl = ToString(GetConfigValue(p, powerFlexSectionName, "connectionUrl", true))
	// optional fields
	var metricWhitelist = ToString(GetConfigValue(p, powerFlexSectionName, "metricWhitelist", false))

	// ----------------- Process the configuration ------------------

	re := regexp.MustCompile(instanceTypeRegex)
	dataEndPoint = string(re.ReplaceAll([]byte(dataEndPoint), []byte(instanceType)))
	idEndPoint = string(re.ReplaceAll([]byte(idEndPoint), []byte(instanceType)))

	config := map[string]string{
		"userName":        userName,
		"password":        password,
		"instanceType":    instanceType,
		"metricPath":      metricPath,
		"metricWhitelist": metricWhitelist,
		"dataEndPoint":    dataEndPoint,
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
	instanceList := make([]string, len(result))

	log.Output(1, "[LOG] Getting instances")
	log.Output(1, string(res))
	log.Output(1, "[LOG] There are total "+fmt.Sprint(len(result))+" instances")

	for _, x := range result {
		dict, ok := x.(map[string]interface{})
		if !ok {
			log.Fatal("[ERROR] Can't convert the result instance to map.")
		}
		instanceList = append(instanceList, ToString(dict["id"]))
	}
	// Fake data
	// instanceList = GetInstList()

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

func processDataFromInstances(instance string, config map[string]string, metrics []string, data *MetricDataReceivePayload) {
	re := regexp.MustCompile(idRegex)
	endPoint := string(re.ReplaceAll([]byte(config["dataEndPoint"]), []byte(instance)))
	var headers map[string]string
	form := url.Values{}
	res := SendRequest(
		http.MethodGet,
		FormCompleteURL(config["connectionUrl"], endPoint),
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
	numOfInst := len(instances)
	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		InstanceDataMap: make(map[string]InstanceData),
	}
	metrics, err := ReadLines("conf.d/" + config["metricPath"])
	if err != nil {
		log.Fatal(err)
	}
	for i := 0; i < numOfInst; i++ {
		log.Output(2, "[LOG] Getting data from instance: ["+instances[i]+"] now.")
		processDataFromInstances(instances[i], config, metrics, &data)
	}
	return data
}
