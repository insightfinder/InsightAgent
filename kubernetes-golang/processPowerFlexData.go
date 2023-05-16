package main

import (
	"bytes"
	"encoding/base64"
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
	"github.com/spacemonkeygo/openssl"
)

var powerFlexSectionName = "powerFlex"
var instanceTypeRegex = `{\$instanceType}`
var idRegex = `{\$id}`
var AUTHAPI = "/Api/V1/Authenticate"

func getConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
	var instanceType = ToString(GetConfigValue(p, powerFlexSectionName, "instanceType", true))
	var metricPath = ToString(GetConfigValue(p, powerFlexSectionName, "metricPath", true))
	var dataEndPoint = ToString(GetConfigValue(p, powerFlexSectionName, "dataEndPoint", true))
	var idEndPoint = ToString(GetConfigValue(p, powerFlexSectionName, "idEndPoint", true))
	var connectionUrl = ToString(GetConfigValue(p, powerFlexSectionName, "connectionUrl", true))
	var domain = ToString(GetConfigValue(p, powerFlexSectionName, "dataEndPoint", true))
	var password = ToString(GetConfigValue(p, powerFlexSectionName, "idEndPoint", true))
	var userName = ToString(GetConfigValue(p, powerFlexSectionName, "connectionUrl", true))
	// optional fields
	var metricWhitelist = ToString(GetConfigValue(p, powerFlexSectionName, "metricWhitelist", false))

	// ----------------- Process the configuration ------------------

	re := regexp.MustCompile(instanceTypeRegex)
	dataEndPoint = string(re.ReplaceAll([]byte(dataEndPoint), []byte(instanceType)))
	idEndPoint = string(re.ReplaceAll([]byte(idEndPoint), []byte(instanceType)))

	config := map[string]string{
		"instanceType":    instanceType,
		"metricPath":      metricPath,
		"metricWhitelist": metricWhitelist,
		"dataEndPoint":    dataEndPoint,
		"idEndPoint":      idEndPoint,
		"connectionUrl":   connectionUrl,
		"domain":          domain,
		"password":        password,
		"userName":        userName,
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
	res := SendRequest(
		http.MethodGet,
		getInstanceEndpoint,
		strings.NewReader(form.Encode()),
		headers,
	)

	var result []interface{}
	json.Unmarshal(res, &result)
	instanceList := make([]string, len(result))

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
	)

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

func authenticationPF(config map[string]string) {
	endPoint := FormCompleteURL(
		config["connectionUrl"], AUTHAPI,
	)
	headers := map[string]string{
		"Content-Type": "application/json",
		"Accept":       "application/json",
	}
	authRequest := AuthRequest{
		Domain:   config["domain"],
		UserName: config["userName"],
		Password: config["password"],
	}
	bytesPayload, _ := json.Marshal(authRequest)
	res := SendRequest(
		http.MethodPost,
		FormCompleteURL(config["connectionUrl"], endPoint),
		bytes.NewBuffer(bytesPayload),
		headers,
	)
	var result AuthResponse
	json.Unmarshal(res, &result)
	apiKey := result.ApiKey
	apiSecret := result.ApiSecret
	timestamp := fmt.Sprint(time.Now().UnixMilli())
	requestStringList := []string{apiKey, http.MethodPost, "/Api/V1/Log", "if-golang/0.1/golang", timestamp}
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
}

func PowerFlexDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	config := getConfig(p)
	authenticationPF(config)
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
		processDataFromInstances(instances[i], config, metrics, &data)
	}
	return data
}
