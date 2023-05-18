package main

import (
	"bufio"
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"strings"

	"github.com/bigkevmcd/go-configparser"
)

var METRIC_DATA_API = "/api/v2/metric-data-receive"
var CHUNK_SIZE = 2 * 1024 * 1024
var MAX_PACKET_SIZE = 10000000

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

	request := MetricPostRequestPayload{
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
	response = SendRequest(
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

func SendRequest(operation string, endpoint string, form io.Reader, headers map[string]string, auth AuthRequest) []byte {
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

	return body
}

func AbsFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	mydir, err := os.Getwd()
	if err != nil {
		fmt.Println(err)
	}
	absFilePath := filepath.Join(mydir, filename)
	return absFilePath
}

func ReadLines(path string) ([]string, error) {
	log.Output(1, "Reading the lines from file "+AbsFilePath(path))
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var lines []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	return lines, scanner.Err()
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
