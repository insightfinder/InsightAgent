package main

import (
	"encoding/json"
	"fmt"
	"log"
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

func getConfig(p *configparser.ConfigParser) map[string]interface{} {
	// required fields
	var instanceType = GetConfigValue(p, powerFlexSectionName, "instanceType", true).(string)
	var metricFields = GetConfigValue(p, powerFlexSectionName, "metricFields", true)
	var dataEndPoint = GetConfigValue(p, powerFlexSectionName, "dataEndPoint", true).(string)
	var idEndPoint = GetConfigValue(p, powerFlexSectionName, "idEndPoint", true).(string)
	var connectionUrl = GetConfigValue(p, powerFlexSectionName, "connectionUrl", true).(string)
	// optional fields
	var metricWhitelist = GetConfigValue(p, powerFlexSectionName, "metricWhitelist", false).(string)

	// ----------------- Process the configuration ------------------

	re := regexp.MustCompile(instanceTypeRegex)
	dataEndPoint = string(re.ReplaceAll([]byte(dataEndPoint), []byte(instanceType)))
	idEndPoint = string(re.ReplaceAll([]byte(idEndPoint), []byte(instanceType)))

	config := map[string]interface{}{
		"instanceType":    instanceType,
		"metricFields":    metricFields,
		"metricWhitelist": metricWhitelist,
		"dataEndPoint":    dataEndPoint,
		"idEndPoint":      idEndPoint,
		"connectionUrl":   connectionUrl,
	}
	return config
}

func getInstanceList(config map[string]interface{}) []string {
	form := url.Values{}
	getInstanceEndpoint := FormCompleteURL(
		config["connectionUrl"].(string), config["idEndPoint"].(string),
	)
	// Header currently left empty
	var headers map[string]string
	res := SendRequest(
		"GET",
		getInstanceEndpoint,
		strings.NewReader(form.Encode()),
		headers,
	)

	var result []interface{}
	json.Unmarshal(res, &result)
	instanceList := make([]string, len(result))
	for _, x := range result {
		instanceList = append(instanceList, x.(map[string]interface{})["id"].(string))
	}
	// Fake data
	// instances := []string{"1", "2", "3", "4", "5"}
	// return instances
	return instanceList
}

func formMetricDataPoint(metric string, value interface{}) MetricDataPoint {
	intVar, err := strconv.ParseFloat(value.(string), 64)
	if err != nil {
		log.Fatal(err)
	}
	metricDP := MetricDataPoint{
		MetricName: metric,
		Value:      intVar,
	}
	return metricDP
}

func processDataFromInstances(instance string, config map[string]interface{}, data *[]map[string]interface{}, pfWG *sync.WaitGroup) map[string]interface{} {
	defer pfWG.Done()
	re := regexp.MustCompile(idRegex)
	endPoint := string(re.ReplaceAll([]byte(config["dataEndPoint"].(string)), []byte(instance)))
	var headers map[string]string
	form := url.Values{}
	res := SendRequest(
		"GET",
		FormCompleteURL(config["connectionUrl"].(string), endPoint),
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
	prasedData := parseData(result, timeStamp, config)
	*data = append(*data, result)
	println(prasedData)
	return result
}

func parseData(data map[string]interface{}, timeStamp int64, config map[string]interface{}) string {
	// Split the metric fields by "," and trim the whitespace
	metrics := strings.Split(strings.ReplaceAll(config["metricFields"].(string), " ", ""), ",")
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
			log.Fatal("Wrong type input from the data")
		}
	}
	instanceData := InstanceData{
		InstanceName:       "333",
		ComponentName:      "tttt",
		DataInTimestampMap: make(map[int64]DataInTimestamp),
	}
	instanceData.DataInTimestampMap[timeStamp] = dataInTs
	jData, _ := json.Marshal(instanceData)
	fmt.Println(string(jData))
	return "res"
}

func PowerFlexDataStream(p *configparser.ConfigParser) interface{} {
	config := getConfig(p)

	instances := getInstanceList(config)
	pfWG := new(sync.WaitGroup)
	numOfInst := len(instances)
	pfWG.Add(numOfInst)
	var data []map[string]interface{}
	for i := 0; i < numOfInst; i++ {
		processDataFromInstances(instances[i], config, &data, pfWG)
	}
	pfWG.Wait()
	return data
}
