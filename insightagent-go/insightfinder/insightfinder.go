package insightfinder

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"
	"strconv"
	"strings"
	"time"
)

const PROJECT_ENDPOINT = "api/v1/check-and-add-custom-project"

var IsDebugMode = false
var DefaultCollectorType = ""

func isValidProjectType(projectType string) bool {
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

func getProjectInstanceAndCloudType(collectorType string) (string, string) {
	switch strings.ToLower(collectorType) {
	case "prometheus":
		return "Prometheus", "Prometheus"
	default:
		return "", ""
	}
}

func getProjectDataType(projectType string) string {
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

func getProjectAgentType(projectType string, isReplay bool, isContainer bool, dynamicMetricType string) string {
	if isContainer {
		if strings.Contains(projectType, "METRIC") {
			if isReplay {
				return "containerReplay"
			} else {
				return "containerStreaming"
			}
		} else {
			if isReplay {
				return "ContainerHistorical"
			} else {
				return "ContainerCustom"
			}
		}
	}

	if isReplay {
		if strings.Contains(projectType, "METRIC") {
			return "MetricFile"
		} else {
			return "LogFile"
		}
	}

	if len(dynamicMetricType) > 0 {
		if strings.ToLower(dynamicMetricType) == "vm" {
			return "DynamicVM"
		} else {
			return "DynamicHost"
		}
	}

	return "Custom"
}

func isProjectExist(ifConfig *IFConfig) bool {
	log.Debug().Msgf("Check if the project named %s exists in the InsightFinder.",
		ifConfig.ProjectName)

	client := createClient(ifConfig)
	endPointUrl := BuildCompleteURL(ifConfig.IFUrl, PROJECT_ENDPOINT)

	client.RetryCount = 2
	client.RetryWaitTime = 5

	client.SetFormData(map[string]string{
		"operation":   "check",
		"userName":    ifConfig.UserName,
		"licenseKey":  ifConfig.LicenseKey,
		"projectName": ifConfig.ProjectName,
	})

	resp, err := client.R().Post(endPointUrl)
	if err != nil {
		panic(fmt.Sprintf("Error checking project: %v", err.Error()))
	}

	if resp.StatusCode() == 200 {
		var result map[string]interface{}
		err := json.Unmarshal(resp.Body(), &result)
		if err != nil {
			panic(fmt.Sprintf("Error parsing response: %v", err.Error()))
		}

		if !ToBool(result["success"]) {
			return false
		}

		return ToBool(result["isProjectExist"])
	}

	return false
}

func createProject(ifConfig *IFConfig) {
	log.Info().Msgf("Creating project %s in the InsightFinder.", ifConfig.ProjectName)

	client := createClient(ifConfig)
	endPointUrl := BuildCompleteURL(ifConfig.IFUrl, PROJECT_ENDPOINT)

	client.RetryCount = 2
	client.RetryWaitTime = 5

	var data = map[string]string{
		"operation": "create",

		"userName":   ifConfig.UserName,
		"licenseKey": ifConfig.LicenseKey,

		"systemName":  ifConfig.SystemName,
		"projectName": ifConfig.ProjectName,

		"instanceType":     ifConfig.InstanceType,
		"projectCloudType": ifConfig.CloudType,
		"dataType":         ifConfig.DataType,
		"insightAgentType": ifConfig.AgentType,

		"samplingInterval":          strconv.Itoa(ifConfig.SamplingInterval / 60),
		"samplingIntervalInSeconds": strconv.Itoa(ifConfig.SamplingInterval),
	}

	client.SetFormData(data)
	resp, err := client.R().Post(endPointUrl)
	if err != nil {
		panic(fmt.Sprintf("Error creating project: %v", err.Error()))
	}

	if resp.StatusCode() == 200 {
		var result map[string]interface{}
		err := json.Unmarshal(resp.Body(), &result)
		if err != nil {
			panic(fmt.Sprintf("Error parsing response: %v", err.Error()))
		}

		if !ToBool(result["success"]) {
			panic(fmt.Sprintf("Error creating project: %v", result))
		}
	} else {
		panic(fmt.Sprintf("Error creating project: %v", resp.String()))
	}
}

func createClient(ifConfig *IFConfig) *resty.Client {
	client := resty.New()
	client.SetTLSClientConfig(&tls.Config{InsecureSkipVerify: true})

	if IsDebugMode {
		client.SetDebug(true)
	}

	for _, value := range ifConfig.IFProxies {
		client.SetProxy(value)
	}

	return client
}

func CheckProject(ifConfig *IFConfig) {
	if !isProjectExist(ifConfig) {
		log.Info().Msgf("Project %s does not exist. Creating...", ifConfig.ProjectName)
		createProject(ifConfig)

		log.Info().Msg("Sleep for 5 seconds to wait for project creation and will check the project existent again.")
		time.Sleep(5 * time.Second)

		if !isProjectExist(ifConfig) {
			panic(fmt.Sprintf("Project %s does not exist after creation.", ifConfig.ProjectName))
		} else {
			log.Info().Msgf("Project %s has been created successfully.", ifConfig.ProjectName)
		}
	} else {
		log.Info().Msgf("Project %s already exists.", ifConfig.ProjectName)
	}
}

func SendMetricData(ifConfig *IFConfig, dataMessages *[]DataMessage) {
	payload := IFMetricPostRequestPayload{
		UserName:   ifConfig.UserName,
		LicenseKey: ifConfig.LicenseKey,
	}

	dataPayload := MetricDataReceivePayload{
		UserName:    ifConfig.UserName,
		ProjectName: ifConfig.ProjectName,
		SystemName:  ifConfig.SystemName,
	}

	instanceDataMap := make(map[string]InstanceData)
	for _, msg := range *dataMessages {
		timestamp, _ := strconv.ParseInt(msg.Timestamp, 10, 64)
		instanceData, ok := instanceDataMap[msg.Instance]
		if !ok {
			instanceData = InstanceData{
				InstanceName:       msg.Instance,
				ComponentName:      msg.ComponentName,
				DataInTimestampMap: make(map[int64]DataInTimestamp),
			}
		}

		dataInTimestampMap := instanceData.DataInTimestampMap
		dataInTimestamp, ok := dataInTimestampMap[timestamp]
		if !ok {
			dataInTimestamp = DataInTimestamp{
				TimeStamp:        timestamp,
				MetricDataPoints: make([]MetricDataPoint, 0),
			}
		}

		metricDataPoints := dataInTimestamp.MetricDataPoints
		value, _ := strconv.ParseFloat(msg.Value, 64)
		metricDataPoints = append(metricDataPoints, MetricDataPoint{
			MetricName: msg.MetricName,
			Value:      value,
		})
	}

	dataPayload.InstanceDataMap = instanceDataMap
	payload.Data = dataPayload

	client := createClient(ifConfig)
	endPointUrl := BuildCompleteURL(ifConfig.IFUrl, "api/v2/metric-data-receive")

	client.R().SetBody(payload).Post(endPointUrl)
}
