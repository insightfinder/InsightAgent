package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

var METRIC_DATA_API = "/api/v2/metric-data-receive"
var CHUNK_SIZE = 2 * 1024 * 1024
var MAX_PACKET_SIZE = 10000000

func FormMetricDataPoint(metric string, value interface{}) (MetricDataPoint, error) {
	intVar, err := strconv.ParseFloat(ToString(value), 64)
	if err != nil {
		return MetricDataPoint{}, err
	}
	metricDP := MetricDataPoint{
		MetricName: metric,
		Value:      intVar,
	}
	return metricDP, nil
}

func ProcessArrayDataFromEndPoint(objArrary []interface{}, timeStampField string, instanceNameField string, data *MetricDataReceivePayload) {
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

func ParseData(data map[string]interface{}, timeStamp int64, metrics []string) DataInTimestamp {
	dataInTs := DataInTimestamp{
		TimeStamp:        timeStamp,
		MetricDataPoints: make([]MetricDataPoint, 0),
	}
	var stack Stack
	if len(metrics) == 0 {
		// if length of the metrics list is 0, get all metrics.
		for key, value := range data {
			stack.Push(MetricStack{
				Metric: value,
				Prefix: key,
			})
		}
	} else {
		for _, metric := range metrics {
			metric = strings.ReplaceAll(metric, " ", "")
			stack.Push(MetricStack{
				Metric: data[metric],
				Prefix: metric,
			})
		}
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
			value, err := FormMetricDataPoint(curPrefix, curVal)
			if err == nil {
				dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, value)
			} else {
				log.Output(1, err.Error())
				log.Output(1, "Failed to cast value"+curVal.(string)+"to number")
			}
		case float64, int64:
			value, err := FormMetricDataPoint(curPrefix, fmt.Sprint(curVal))
			if err == nil {
				dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, value)
			} else {
				log.Output(1, err.Error())
				log.Output(1, "Failed to cast value"+curVal.(string)+"to number")
			}
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

func ProcessMetricData(data MetricDataReceivePayload, IFconfig map[string]interface{}) {
	curTotal := 0
	var newPayload = MetricDataReceivePayload{
		ProjectName:     data.ProjectName,
		UserName:        data.UserName,
		InstanceDataMap: make(map[string]InstanceData),
		SystemName:      ToString(IFconfig["systemName"]),
	}
	for instanceName, istData := range data.InstanceDataMap {
		instanceData, ok := newPayload.InstanceDataMap[instanceName]
		if !ok {
			// Current Instance didn't exist
			instanceData = InstanceData{
				InstanceName:       istData.InstanceName,
				ComponentName:      istData.InstanceName,
				DataInTimestampMap: make(map[int64]DataInTimestamp),
			}
			newPayload.InstanceDataMap[instanceName] = instanceData
		}
		for timeStamp, tsData := range istData.DataInTimestampMap {
			// Need to send out the data in the same timestamp in one payload
			dataBytes, err := json.Marshal(tsData)
			if err != nil {
				log.Fatal("[ERORR] There's issue form json data for DataInTimestampMap.")
			}
			// Add the data into the payload
			instanceData.DataInTimestampMap[timeStamp] = tsData
			// The json.Marshal transform the data into bytes so the length will be the actual size.
			curTotal += len(dataBytes)
			if curTotal > CHUNK_SIZE {
				SendMetricDataToIF(newPayload, IFconfig)
				curTotal = 0
				newPayload = MetricDataReceivePayload{
					ProjectName:     data.ProjectName,
					UserName:        data.UserName,
					InstanceDataMap: make(map[string]InstanceData),
					SystemName:      ToString(IFconfig["systemName"]),
				}
				newPayload.InstanceDataMap[instanceName] = InstanceData{
					InstanceName:       istData.InstanceName,
					ComponentName:      istData.InstanceName,
					DataInTimestampMap: make(map[int64]DataInTimestamp),
				}
			}
		}
	}
	SendMetricDataToIF(newPayload, IFconfig)
}

func SendMetricDataToIF(data MetricDataReceivePayload, config map[string]interface{}) {
	log.Output(1, "-------- Sending data to InsightFinder --------")

	request := IFMetricPostRequestPayload{
		LicenseKey: ToString(config["licenseKey"]),
		UserName:   ToString(config["userName"]),
		Data:       data,
	}
	jData, err := json.Marshal(request)
	if err != nil {
		log.Fatal(err)
	}
	if len(jData) > MAX_PACKET_SIZE {
		log.Fatal("[ERROR]The packet size is too large.")
	}
	var response []byte
	headers := map[string]string{
		"Content-Type": "application/json",
	}
	log.Output(2, "[LOG] Prepare to send out "+fmt.Sprint(len(jData))+" bytes data to IF.")
	log.Output(2, string(jData))
	response, _ = SendRequest(
		http.MethodPost,
		FormCompleteURL(ToString(config["ifURL"]), METRIC_DATA_API),
		bytes.NewBuffer(jData),
		headers,
		AuthRequest{},
	)
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	if ToBool(result["success"]) {
		log.Output(1, "[LOG] Sending data to the InsightFinder successfully.")
	} else {
		log.Output(1, "[ERROR] Failed to send data to the InsightFinder.")
	}
}

func SendRequest(operation string, endpoint string, form io.Reader, headers map[string]string, auth AuthRequest) ([]byte, http.Header) {
	newRequest, err := http.NewRequest(
		operation,
		endpoint,
		form,
	)
	if auth.Password != "" {
		newRequest.SetBasicAuth(auth.UserName, auth.Password)
	}
	if err != nil {
		log.Fatal(err)
	}

	for k := range headers {
		newRequest.Header.Add(k, headers[k])
	}

	// Skip certificate verification.
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	client := &http.Client{Transport: tr}
	res, err := client.Do(newRequest)
	if err != nil {
		log.Fatal(err)
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)

	return body, res.Header
}

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	mydir, err := filepath.Abs(filepath.Dir(os.Args[0]))
	if err != nil {
		log.Fatal(err)
	}
	absFilePath := filepath.Join(mydir, filename)
	return absFilePath
}

func GetEndpointMetricMapping(path string) (map[string][]string, error) {
	jsonFile, err := os.Open(AbsFilePath("conf.d/" + path))
	if err != nil {
		return nil, err
	}
	byteValue, err := ioutil.ReadAll(jsonFile)
	if err != nil {
		return nil, err
	}
	var endPointMapping map[string][]string
	json.Unmarshal(byteValue, &endPointMapping)
	return endPointMapping, nil
}

func GetConfigValue(p *configparser.ConfigParser, section string, param string, required bool) interface{} {
	result, err := p.Get(section, param)
	if err != nil && required {
		log.Fatal(err)
	}
	if result == "" && required {
		log.Fatal("[ERROR] InsightFinder configuration [", param, "] is required!")
	}
	return result
}

func FormCompleteURL(link string, endpoint string) string {
	postUrl, err := url.Parse(link)
	if err != nil {
		log.Output(1, "[ERROR] Fail to pares the URL. Please check your config.")
		log.Fatal(err)
	}
	postUrl.Path = path.Join(postUrl.Path, endpoint)
	return postUrl.String()
}

func ToString(inputVar interface{}) string {
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "string" {
		return inputVar.(string)
	}
	log.Fatal("[ERROR] Wrong input type. Can not convert current input to string.")
	return ""
}

func ToBool(inputVar interface{}) bool {
	if inputVar == nil {
		return false
	}
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "bool" {
		return inputVar.(bool)
	}
	log.Fatal("[ERROR] Wrong input type. Can not convert current input to boolean.")
	return false
}

// ------------------ Project Type transformation ------------------------

func ProjectTypeToAgentType(projectType string, isReplay bool) string {
	if isReplay {
		if strings.Contains(projectType, "METRIC") {
			return "MetricFile"
		} else {
			return "LogFile"
		}
	}
	return "Custom"
}

func IsValidProjectType(projectType string) bool {
	switch projectType {
	case
		"METRIC",
		"METRICREPLAY",
		"LOG",
		"LOGREPLAY",
		"INCIDENT",
		"INCIDENTREPLAY",
		"ALERT",
		"ALERTREPLAY",
		"DEPLOYMENT",
		"DEPLOYMENTREPLAY",
		"TRACE",
		"TRAVEREPLAY":
		return true
	}
	return false
}

func ProjectTypeToDataType(projectType string) string {
	switch projectType {
	case "METRIC":
		return "Metric"
	case "METRICREPLAY":
		return "Metric"
	case "ALERT":
		return "Alert"
	case "INCIDENT":
		return "Incident"
	case "DEPLOYMENT":
		return "Deployment"
	case "TRACE":
		return "Trace"
	default:
		return "Log"
	}
}

// -------------------- The stack type data structure ---------------------
type MetricStack struct {
	Metric interface{}
	Prefix string
}

type Stack []MetricStack

// IsEmpty: check if stack is empty
func (s *Stack) IsEmpty() bool {
	return len(*s) == 0
}

// Push a new value onto the stack
func (s *Stack) Push(stk MetricStack) {
	*s = append(*s, stk) // Simply append the new value to the end of the stack
}

// Remove and return top element of stack. Return false if stack is empty.
func (s *Stack) Pop() (MetricStack, bool) {
	if s.IsEmpty() {
		return MetricStack{}, false
	} else {
		index := len(*s) - 1   // Get the index of the top most element.
		element := (*s)[index] // Index into the slice and obtain the element.
		*s = (*s)[:index]      // Remove it from the stack by slicing it off.
		return element, true
	}
}