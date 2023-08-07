package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"github.com/bigkevmcd/go-configparser"
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
)

const METRIC_DATA_API = "/api/v2/metric-data-receive"
const LOG_DATA_API = "/customprojectrawdata"
const LOG_DATA_AGENT_TYPE = "Stream"
const CHUNK_SIZE = 2 * 1024 * 1024
const MAX_PACKET_SIZE = 10000000

func formMetricDataPoint(metric string, value interface{}) (MetricDataPoint, error) {
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

func processArrayDataFromEndPoint(objArrary []interface{}, metricList []string, timeStampField string, tsFormat string, instanceNameField string, data *MetricDataReceivePayload) {
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
			panic("[ERROR] Can't parse the object array with index: " +
				fmt.Sprint(index))
		}
		// Get timeStamp in epoch milli-second format
		var tsInInt64 int64
		switch tsFormat {
		case "Epoch":
			switch object[timeStampField].(type) {
			case int64:
				tsInInt64 = object[timeStampField].(int64)
			case float64:
				tsInInt64 = int64(object[timeStampField].(float64))
			}
		default:
			parsedTime, err := time.Parse(tsFormat, object[timeStampField].(string))
			if err != nil {
				panic(err.Error())
			}
			tsInInt64 = parsedTime.Unix()
		}
		if tsInInt64 == 0 {
			panic("Can't get timeStamp from timestamp field" + object[timeStampField].(string))
		}
		timeStamp := time.Unix(tsInInt64, 0).UnixMilli()

		prasedData := parseData(object, timeStamp, metricList)
		instance, success := object[instanceNameField].(string)
		if !success {
			panic("[ERROR] Failed to get instance name from the field: " + instanceNameField)
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

func parseData(data map[string]interface{}, timeStamp int64, metrics []string) DataInTimestamp {
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
			value, err := formMetricDataPoint(curPrefix, curVal)
			if err == nil {
				dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, value)
			} else {
				log.Output(1, err.Error())
				log.Output(1, "Failed to cast value "+fmt.Sprint(curVal)+" to number")
			}
		case uint8, uint16, uint32, uint64, int, int8, int16, int32, int64, float32, float64:
			value, err := formMetricDataPoint(curPrefix, fmt.Sprint(curVal))
			if err == nil {
				dataInTs.MetricDataPoints = append(dataInTs.MetricDataPoints, value)
			} else {
				log.Output(1, err.Error())
				log.Output(1, "Failed to cast value "+curVal.(string)+" to number")
			}
		case interface{}:
			curMetricMap, success := curVal.(map[string]interface{})
			if !success {
				log.Output(1, "[ERROR] Can't parse the metric "+curPrefix)
			}
			for k, v := range curMetricMap {
				stack.Push(MetricStack{
					Metric: v,
					Prefix: curPrefix + "." + k,
				})
			}
		default:
			log.Output(1, "[ERROR] Wrong type input from the data. Key:"+
				curPrefix+" ;Value: "+fmt.Sprint(curVal))
		}
	}
	return dataInTs
}

func sendLogData(data []LogData, IFConfig map[string]interface{}) {
	curTotal := 0
	curData := make([]LogData, 0)
	for _, log := range data {
		if curTotal > CHUNK_SIZE {
			jData, err := json.Marshal(
				LogDataReceivePayload{
					UserName:         ToString(IFConfig["userName"]),
					LicenseKey:       ToString(IFConfig["licenseKey"]),
					ProjectName:      ToString(IFConfig["projectName"]),
					SystemName:       ToString(IFConfig["systemName"]),
					InsightAgentType: "LogStreaming",
					LogDataList:      curData,
				},
			)
			if err != nil {
				panic(err.Error())
			}
			sendDataToIF(jData, LOG_DATA_API, IFConfig)
			curTotal = 0
			curData = make([]LogData, 0)
		}
		curData = append(curData, log)
		dataBytes, _ := json.Marshal(log)
		curTotal += len(dataBytes)
	}
	jData, err := json.Marshal(
		LogDataReceivePayload{
			UserName:         ToString(IFConfig["userName"]),
			LicenseKey:       ToString(IFConfig["licenseKey"]),
			ProjectName:      ToString(IFConfig["projectName"]),
			SystemName:       ToString(IFConfig["systemName"]),
			InsightAgentType: "LogStreaming",
			LogDataList:      curData,
		},
	)
	if err != nil {
		panic(err.Error())
	}
	sendDataToIF(jData, LOG_DATA_API, IFConfig)
}

func sendMetricData(data MetricDataReceivePayload, IFconfig map[string]interface{}) {
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
				panic("[ERORR] There's issue form json data for DataInTimestampMap.")
			}
			// Add the data into the payload
			instanceData.DataInTimestampMap[timeStamp] = tsData
			// The json.Marshal transform the data into bytes so the length will be the actual size.
			curTotal += len(dataBytes)
			if curTotal > CHUNK_SIZE {
				request := IFMetricPostRequestPayload{
					LicenseKey: ToString(IFconfig["licenseKey"]),
					UserName:   ToString(IFconfig["userName"]),
					Data:       data,
				}
				jData, err := json.Marshal(request)
				if err != nil {
					panic(err)
				}
				sendDataToIF(jData, METRIC_DATA_API, IFconfig)
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
	request := IFMetricPostRequestPayload{
		LicenseKey: ToString(IFconfig["licenseKey"]),
		UserName:   ToString(IFconfig["userName"]),
		Data:       data,
	}
	jData, err := json.Marshal(request)
	if err != nil {
		panic(err)
	}
	sendDataToIF(jData, METRIC_DATA_API, IFconfig)
}

func sendDataToIF(data []byte, receiveEndpoint string, config map[string]interface{}) {
	log.Output(1, "-------- Sending data to InsightFinder --------")

	if len(data) > MAX_PACKET_SIZE {
		panic("[ERROR]The packet size is too large.")
	}

	endpoint := FormCompleteURL(ToString(config["ifURL"]), receiveEndpoint)
	var response []byte
	headers := map[string]string{
		"Content-Type": "application/json",
	}
	if receiveEndpoint == LOG_DATA_API {
		headers["agent-type"] = LOG_DATA_AGENT_TYPE
	}
	log.Output(2, "[LOG] Prepare to send out "+fmt.Sprint(len(data))+" bytes data to IF:"+endpoint)
	response, _ = sendRequest(
		http.MethodPost,
		endpoint,
		bytes.NewBuffer(data),
		headers,
		false,
	)
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	if ToBool(result["success"]) {
		log.Output(1, "[LOG] Sending data to the InsightFinder successfully.")
	} else {
		log.Output(1, "[ERROR] Failed to send data to the InsightFinder."+fmt.Sprint(string(response)))
	}
}

func sendRequest(operation string, endpoint string, form io.Reader, headers map[string]string, skipCertificate bool) ([]byte, http.Header) {
	newRequest, err := http.NewRequest(
		operation,
		endpoint,
		form,
	)
	if err != nil {
		panic(err)
	}

	for k := range headers {
		newRequest.Header.Add(k, headers[k])
	}
	var client *http.Client
	// If we will skip certificate verification.
	if !skipCertificate {
		client = &http.Client{}
	} else {
		tr := &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: skipCertificate},
		}
		client = &http.Client{Transport: tr}
	}

	res, err := client.Do(newRequest)
	if err != nil {
		panic(err)
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)

	return body, res.Header
}

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	curdir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	mydir, err := filepath.Abs(curdir)
	if err != nil {
		panic(err)
	}
	return filepath.Join(mydir, filename)
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
		panic(err)
	}
	if result == "" && required {
		panic("[ERROR] InsightFinder configuration [" + param + "] is required!")
	}
	return result
}

func FormCompleteURL(link string, endpoint string) string {
	postUrl, err := url.Parse(link)
	if err != nil {
		log.Output(1, "[ERROR] Fail to pares the URL. Please check your config.")
		panic(err)
	}
	postUrl.Path = path.Join(postUrl.Path, endpoint)
	return postUrl.String()
}

func ToString(inputVar interface{}) string {
	if inputVar == nil {
		return ""
	}
	return fmt.Sprint(inputVar)
}

func ToBool(inputVar interface{}) bool {
	if inputVar == nil {
		return false
	}
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "bool" {
		return inputVar.(bool)
	}
	panic("[ERROR] Wrong input type. Can not convert current input to boolean.")
}

func ToInt(inputVar interface{}) int {
	if inputVar == nil {
		return 0
	}
	mtype := reflect.TypeOf(inputVar)
	if fmt.Sprint(mtype) == "int" {
		return inputVar.(int)
	}
	panic("[ERROR] Wrong input type. Can not convert current input to int.")
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

func copyMap[K, V comparable](m map[K]V) map[K]V {
	result := make(map[K]V)
	for k, v := range m {
		result[k] = v
	}
	return result
}

func copyAnyMap(m map[string]interface{}) map[string]interface{} {
	cp := make(map[string]interface{})
	for k, v := range m {
		vm, ok := v.(map[string]interface{})
		if ok {
			cp[k] = copyAnyMap(vm)
		} else {
			cp[k] = v
		}
	}

	return cp
}
