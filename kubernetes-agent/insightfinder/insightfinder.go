package insightfinder

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

const METRIC_DATA_API = "/api/v2/metric-data-receive"
const LOG_DATA_API = "/customprojectrawdata"
const LOG_DATA_AGENT_TYPE = "Stream"
const CHUNK_SIZE = 2 * 1024 * 1024
const MAX_PACKET_SIZE = 10000000
const HTTP_RETRY_TIMES = 15
const HTTP_RETRY_INTERVAL = 60

func SendLogData(data []LogData, IFConfig map[string]interface{}) {
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
			SendDataToIF(jData, LOG_DATA_API, IFConfig)
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
	SendDataToIF(jData, LOG_DATA_API, IFConfig)
}

func SendMetricData(data MetricDataReceivePayload, IFconfig map[string]interface{}) {
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
			// Current NodeInstance didn't exist
			instanceData = InstanceData{
				InstanceName:       istData.InstanceName,
				ComponentName:      istData.ComponentName,
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
				SendDataToIF(jData, METRIC_DATA_API, IFconfig)
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
	SendDataToIF(jData, METRIC_DATA_API, IFconfig)
}

func SendDataToIF(data []byte, receiveEndpoint string, config map[string]interface{}) {
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
	response, _ = SendRequest(
		http.MethodPost,
		endpoint,
		bytes.NewBuffer(data),
		headers,
		AuthRequest{},
	)
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	log.Output(1, string(response))
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
		panic(err)
	}
	for k := range headers {
		newRequest.Header.Add(k, headers[k])
	}
	// Skip certificate verification.
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}

	client := &http.Client{Transport: tr}
	var res *http.Response
	for i := 0; i < HTTP_RETRY_TIMES; i++ {
		res, err = client.Do(newRequest)
		if err == nil {
			break // Request successful, exit the loop
		}
		fmt.Printf("Error occurred: %v\n", err)
		time.Sleep(HTTP_RETRY_INTERVAL * time.Second)
		fmt.Printf("Sleep for " + fmt.Sprint(HTTP_RETRY_INTERVAL) + " seconds and retry .....")
	}
	if err != nil {
		log.Output(1, "[ERROR] HTTP connection failure after 10 times of retry.")
		panic(err)
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)
	return body, res.Header
}
