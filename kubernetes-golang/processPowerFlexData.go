package main

import (
	"encoding/json"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

var powerFlexSectionName = "powerFlex"
var instanceTypeRegex = `{\$instanceType}`
var idRegex = `{\$id}`

func getConfig(p *configparser.ConfigParser) map[string]string {
	// required fields
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
	// instanceList = []string{"instance1", "instance12", "instance13", "instance14", "instance15"}

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

func processDataFromInstances(instance string, config map[string]string, metrics []string, data *MetricDataReceivePayload, pfWG *sync.WaitGroup) {
	defer pfWG.Done()
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
	// res := []byte(`{
	// 			"id": "1",
	// 			"name": "6444",
	// 			"department": "shopping",
	// 			"designation": {
	// 				"test": "1"
	// 			}
	// 			}`)

	var result map[string]interface{}
	json.Unmarshal([]byte(res), &result)
	prasedData := parseData(result, timeStamp, metrics)

	instanceData := InstanceData{
		InstanceName:       instance,
		ComponentName:      "NO_COMPONENT_NAME",
		DataInTimestampMap: make(map[int64]DataInTimestamp),
	}
	instanceData.DataInTimestampMap[timeStamp] = prasedData
	data.InstanceDataMap[instance] = instanceData
}

func parseData(data map[string]interface{}, timeStamp int64, metrics []string) DataInTimestamp {
	dataInTs := DataInTimestamp{
		TimeStamp:        timeStamp,
		MetricDataPoints: make([]MetricDataPoint, 0),
	}
	var stack Stack
	for _, metric := range metrics {
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

func PowerFlexDataStream(p *configparser.ConfigParser, IFconfig map[string]interface{}) MetricDataReceivePayload {
	config := getConfig(p)

	instances := getInstanceList(config)
	pfWG := new(sync.WaitGroup)
	numOfInst := len(instances)
	pfWG.Add(numOfInst)
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
		go processDataFromInstances(instances[i], config, metrics, &data, pfWG)
	}
	pfWG.Wait()
	return data
}
