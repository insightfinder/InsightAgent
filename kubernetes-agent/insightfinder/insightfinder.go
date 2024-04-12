package insightfinder

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"github.com/carlmjohnson/requests"
	"io"
	"log"
	"log/slog"
	"net/http"
	"os"
	"time"
)

const METRIC_DATA_API = "/api/v2/metric-data-receive"
const LOG_DATA_API = "/api/v1/customprojectrawdata"
const LOG_DATA_AGENT_TYPE = "Stream"
const CHUNK_SIZE = 2 * 1024 * 1024
const MAX_PACKET_SIZE = 10000000
const HTTP_RETRY_TIMES = 15
const HTTP_RETRY_INTERVAL = 60

func SendLogData(data *[]LogData, IFConfig map[string]interface{}) {

	// Skip sending if there's no data
	if len(*data) == 0 {
		return
	}

	curTotal := 0
	curData := make([]LogData, 0)
	for _, logEntry := range *data {
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
		curData = append(curData, logEntry)
		dataBytes, _ := json.Marshal(logEntry)
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

func SendMetricData(data *MetricDataReceivePayload, IFconfig map[string]interface{}) {
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
					Data:       *data,
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
		Data:       *data,
	}
	jData, err := json.Marshal(request)
	if err != nil {
		panic(err)
	}
	SendDataToIF(jData, METRIC_DATA_API, IFconfig)
}

func SendDataToIF(data []byte, receiveEndpoint string, config map[string]interface{}) {
	slog.Info("-------- Sending data to InsightFinder --------")

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
	slog.Info("[LOG] Prepare to send out " + fmt.Sprint(len(data)) + " bytes data to IF:" + endpoint)
	response, _ = SendRequest(
		http.MethodPost,
		endpoint,
		bytes.NewBuffer(data),
		headers,
		AuthRequest{},
	)
	var result map[string]interface{}
	json.Unmarshal(response, &result)
	slog.Info(string(response))
}

func SendDependencyMap(data *[]map[string]string, IFconfig map[string]interface{}) {
	componentRelationList := make([]DependencyRelationPair, 0)
	for _, componentRelation := range *data {
		source := DependencyRelationEntity{
			Id:   componentRelation["Source"],
			Type: "componentLevel",
		}

		target := DependencyRelationEntity{
			Id:   componentRelation["Target"],
			Type: "componentLevel",
		}

		pair := DependencyRelationPair{
			S: source,
			T: target,
		}
		componentRelationList = append(componentRelationList, pair)
	}
	componentRelationListStr, _ := json.Marshal(componentRelationList)

	// Send the data to IF
	req := DependencyRelationPayload{
		SystemDisplayName:             ToString(IFconfig["systemName"]),
		LicenseKey:                    ToString(IFconfig["licenseKey"]),
		UserName:                      ToString(IFconfig["userName"]),
		DailyTimestamp:                time.Now().UnixMilli(),
		ProjectLevelAddRelationSetStr: string(componentRelationListStr),
	}

	PrintStruct(req, false, IFconfig["projectName"].(string)+".json")
	var res string
	url := ToString(IFconfig["ifURL"]) + "/api/v2/updaterelationdependency"

	err := requests.
		URL(url).
		Post().
		BodyJSON(&req).
		ToString(&res).
		Fetch(context.Background())
	if err != nil {
		println(err.Error())
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
		slog.Info("[ERROR] HTTP connection failure after 10 times of retry.")
		panic(err)
	}

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)
	return body, res.Header
}

func PrintStruct(v any, needPrint bool, fileName string) {
	jsonBytes, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		log.Fatalf("JSON marshaling failed: %s", err)
	}
	if needPrint {
		fmt.Println(string(jsonBytes))
	}
	err = os.WriteFile("PrintStruct-"+fileName+".json", jsonBytes, 0644)
	if err != nil {
		log.Fatalf("Writing to file failed: %s", err)
	}
}
