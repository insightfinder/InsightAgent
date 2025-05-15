package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"io"
	"log"
	"net/http"
	"net/url"
	"path"
	"reflect"
	"strconv"
	"strings"
	"time"
)

const ProjectEndPoint = "api/v1/check-and-add-custom-project"
const MetricDataApi = "/api/v2/metric-data-receive"
const LogDataApi = "/customprojectrawdata"
const LogDataAgentType = "Stream"
const ChunkSize = 2 * 1024 * 1024
const MaxPacketSize = 10000000

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
		log.Printf("[ERROR] Fail to pares the URL. Please check your config.")
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
		return "Log"
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

func sendDataToIF(data []byte, receiveEndpoint string, config map[string]interface{}) {
	log.Printf("-------- Sending data to InsightFinder --------\n")

	println(string(data))

	if len(data) > MaxPacketSize {
		panic("[ERROR] The packet size is too large.")
	}

	endpoint := FormCompleteURL(ToString(config["ifURL"]), receiveEndpoint)
	var response []byte
	headers := map[string]string{
		"Content-Type": "application/json",
	}
	if receiveEndpoint == LogDataApi {
		headers["agent-type"] = LogDataAgentType
	}
	log.Printf("Prepare to send out %s bytes data to IF:%s\n", ToString(len(data)), endpoint)
	response, _ = sendRequest(http.MethodPost, endpoint, bytes.NewBuffer(data), headers, false)

	var result map[string]interface{}
	_ = json.Unmarshal(response, &result)
	if ToBool(result["success"]) {
		log.Printf("Sending data to the InsightFinder successfully.\n")
	} else {
		log.Printf("[ERROR] Failed to send data to the InsightFinder.%s\n", response)
	}
}

func sendMetricData(instanceDataMap map[string]InstanceData, IFconfig map[string]interface{}) {

	projectName := ToString(IFconfig["projectName"])
	userName := ToString(IFconfig["userName"])
	systemName := ToString(IFconfig["systemName"])
	licenseKey := ToString(IFconfig["licenseKey"])

	curTotal := 0
	data := MetricDataReceivePayload{
		ProjectName:     projectName,
		UserName:        userName,
		SystemName:      systemName,
		InstanceDataMap: make(map[string]InstanceData),
	}

	for instanceName, instData := range instanceDataMap {
		instanceData, ok := data.InstanceDataMap[instanceName]
		if !ok {
			// Current Instance didn't exist
			instanceData = InstanceData{
				InstanceName:       instanceName,
				ComponentName:      instanceName,
				DataInTimestampMap: make(map[int64]DataInTimestamp),
			}
			data.InstanceDataMap[instanceName] = instanceData
		}

		for timeStamp, tsData := range instData.DataInTimestampMap {
			// Need to send out the data in the same timestamp in one payload
			dataBytes, err := json.Marshal(tsData)
			if err != nil {
				panic("[ERORR] There's issue form json data for DataInTimestampMap.")
			}

			// Add the data into the payload
			instanceData.DataInTimestampMap[timeStamp] = tsData
			// The json.Marshal transform the data into bytes so the length will be the actual size.
			curTotal += len(dataBytes)

			if curTotal > ChunkSize {
				request := IFMetricPostRequestPayload{
					LicenseKey: licenseKey,
					UserName:   userName,
					Data:       data,
				}

				jData, err := json.Marshal(request)
				if err != nil {
					panic(err)
				}

				sendDataToIF(jData, MetricDataApi, IFconfig)

				// reset the data
				curTotal = 0
				data = MetricDataReceivePayload{
					ProjectName:     projectName,
					UserName:        userName,
					InstanceDataMap: make(map[string]InstanceData),
					SystemName:      systemName,
				}
				data.InstanceDataMap[instanceName] = InstanceData{
					InstanceName:       instanceName,
					ComponentName:      instanceName,
					DataInTimestampMap: make(map[int64]DataInTimestamp),
				}
			}
		}
	}

	request := IFMetricPostRequestPayload{
		LicenseKey: licenseKey,
		UserName:   userName,
		Data:       data,
	}
	jData, err := json.Marshal(request)
	if err != nil {
		panic(err)
	}
	sendDataToIF(jData, MetricDataApi, IFconfig)
}

func checkProject(IFconfig map[string]interface{}) {
	projectName := ToString(IFconfig["projectName"])

	if len(projectName) > 0 {
		if !isProjectExist(IFconfig) {

			log.Printf("Didn't find the project named %s. Start creating project in the InsightFinder.\n", projectName)

			createProject(IFconfig)

			log.Printf("Sleep for 5 seconds to wait for project creation and will check the project exisitense again.")

			time.Sleep(time.Second * 5)

			if !isProjectExist(IFconfig) {
				panic("[ERROR] Fail to create project " + projectName)
			}
			log.Printf(fmt.Sprintf("Create project %s successfully!", projectName))
		} else {
			log.Printf(fmt.Sprintf("Project named %s exist. Program will continue.", projectName))
		}
	}
}

func isProjectExist(IFconfig map[string]interface{}) bool {
	projectName := ToString(IFconfig["projectName"])

	log.Printf("Check if the project named %s exists in the InsightFinder.", projectName)

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", ToString(IFconfig["userName"]))
	form.Add("licenseKey", ToString(IFconfig["licenseKey"]))
	form.Add("projectName", projectName)

	headers := map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	}

	endpoint := FormCompleteURL(ToString(IFconfig["ifURL"]), ProjectEndPoint)
	response, _ := sendRequest(http.MethodPost, endpoint, strings.NewReader(form.Encode()), headers, false)

	var result map[string]interface{}
	err := json.Unmarshal(response, &result)
	if err != nil {
		panic("[ERROR] Check project exist failed. Please check your parameters.")
	}

	if !ToBool(result["success"]) {
		panic("[ERROR] Check project exist failed. Please check your parameters.")
	}

	return ToBool(result["isProjectExist"])
}

func createProject(IFconfig map[string]interface{}) {

	projectName := ToString(IFconfig["projectName"])
	projectType := ToString(IFconfig["projectType"])

	log.Printf("Creating the project named %s in the InsightFinder.", projectName)

	form := url.Values{}
	form.Add("operation", "create")
	form.Add("userName", ToString(IFconfig["userName"]))
	form.Add("licenseKey", ToString(IFconfig["licenseKey"]))
	form.Add("projectName", projectName)

	if IFconfig["systemName"] != nil {
		form.Add("systemName", ToString(IFconfig["systemName"]))
	} else {
		form.Add("systemName", projectName)
	}
	form.Add("instanceType", "PrivateCloud")
	form.Add("projectCloudType", "PrivateCloud")
	form.Add("dataType", ProjectTypeToDataType(projectType))
	form.Add("insightAgentType", ProjectTypeToAgentType(projectType, false))
	form.Add("samplingInterval", ToString(IFconfig["samplingInterval"]))
	form.Add("samplingIntervalInSeconds", ToString(IFconfig["samplingInterval"]))

	samplingIntervalINT, err := strconv.Atoi(ToString(IFconfig["samplingInterval"]))

	if err != nil {
		panic(err)
	}

	form.Add("samplingIntervalInSeconds", fmt.Sprint(samplingIntervalINT*60))
	headers := map[string]string{
		"Content-Type": "application/x-www-form-urlencoded",
	}
	endpoint := FormCompleteURL(ToString(IFconfig["ifURL"]), ProjectEndPoint)

	response, _ := sendRequest(http.MethodPost, endpoint, strings.NewReader(form.Encode()), headers, false)
	var result map[string]interface{}
	_ = json.Unmarshal(response, &result)
}
