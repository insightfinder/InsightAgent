package insightfinder

import (
	"context"
	"fmt"
	"github.com/carlmjohnson/requests"
	"github.com/google/go-querystring/query"
	ifrequest "grafana-agent/service/insightfinder/models/request"
	ifresponse "grafana-agent/service/insightfinder/models/response"
	"log/slog"
	"net/url"
)

const PROJECT_API = "/api/v1/check-and-add-custom-project"
const METRIC_DATA_API = "/api/v2/metric-data-receive"
const LOG_DATA_API = "/api/v1/customprojectrawdata"
const CHUNK_SIZE = 2 * 1024 * 1024
const MAX_PACKET_SIZE = 10000000

type InsightFinder struct {
	Endpoint         string
	Username         string
	LicenseKey       string
	ProjectName      string
	CloudType        string
	InstanceType     string
	SystemName       string
	ProjectType      string // "Metric", "Log", "Trace", "Deployment", "Alert", "Incident"
	DataType         string
	Container        bool
	InsightAgentType string
	SamplingInterval uint // In seconds
}

func NewInsightFinder(endpoint string, username string, licenseKey string, projectName string, projectType string, systemName string) InsightFinder {
	insightfinder := InsightFinder{Endpoint: endpoint, Username: username, LicenseKey: licenseKey, ProjectName: projectName, ProjectType: projectType, SystemName: systemName}
	insightfinder.Validate()
	return insightfinder
}

func (ifclient *InsightFinder) Validate() bool {

	if ifclient.Endpoint == "" {
		slog.Error("Endpoint is required")
		return false
	}
	if ifclient.Username == "" {
		slog.Error("Username is required")
		return false
	}
	if ifclient.LicenseKey == "" {
		slog.Error("LicenseKey is required")
		return false
	}
	if ifclient.ProjectName == "" {
		slog.Error("ProjectName is required")
		return false
	}
	if ifclient.SystemName == "" {
		slog.Warn("SystemName is not set, defaulting to ProjectName.") // Add missing argument ifclient.ProjectName
		ifclient.SystemName = ifclient.ProjectName
	}

	if ifclient.CloudType == "" {
		ifclient.CloudType = "PrivateCloud"
		slog.Warn("CloudType is not set, defaulting to PrivateCloud")
	}

	if ifclient.InstanceType == "" {
		ifclient.InstanceType = "PrivateCloud"
		slog.Warn("InstanceType is not set, defaulting to PrivateCloud")
	}

	// Assign DataType based on ProjectType
	ifclient.DataType = ifclient.ProjectType

	// Assign Default SamplingInterval
	if ifclient.SamplingInterval == 0 {
		ifclient.SamplingInterval = 5 * 60
	}

	// Assign InsightAgentType based on ProjectType and Container
	if ifclient.ProjectType == "Metric" {
		if ifclient.Container {
			ifclient.InsightAgentType = "containerStreaming"
		} else {
			ifclient.InsightAgentType = "Custom"
		}
	} else {
		if ifclient.Container {
			ifclient.InsightAgentType = "ContainerCustom"
		} else {
			ifclient.InsightAgentType = "Custom"
		}
	}

	return true
}

func (ifclient *InsightFinder) CreateProjectIfNotExist() bool {
	if !ifclient.IsProjectExist() {
		return ifclient.CreateProject()
	}
	return true
}

func (ifclient *InsightFinder) CreateProject() bool {
	request := ifrequest.CheckAndAddCustomProjectRequest{
		Operation:        "create",
		UserName:         ifclient.Username,
		LicenseKey:       ifclient.LicenseKey,
		ProjectName:      ifclient.ProjectName,
		SystemName:       ifclient.SystemName,
		InstanceType:     ifclient.InstanceType,
		ProjectCloudType: ifclient.CloudType,
		DataType:         ifclient.DataType,
		InsightAgentType: ifclient.InsightAgentType,
		SamplingInterval: int(ifclient.SamplingInterval),
	}
	requestForm, err := query.Values(request)
	if err != nil {
		slog.Error("Error building request form to create project.", err)
		return false
	}

	var resultStr string
	err = requests.URL(ifclient.Endpoint).Path(PROJECT_API).Header("agent-type", "Stream").BodyJSON(request).Params(requestForm).ToString(&resultStr).Post().Fetch(context.Background())
	if err != nil {
		fmt.Println(err)
		return false
	}

	slog.Info(fmt.Sprintf("Project '%s' created in the InsightFinder.", ifclient.ProjectName))
	return true
}

func (ifclient *InsightFinder) IsProjectExist() bool {
	// Check if the project exists
	slog.Info(fmt.Sprintf("Check if the project '%s' exists in the InsightFinder.", ifclient.ProjectName))

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", ifclient.Username)
	form.Add("licenseKey", ifclient.LicenseKey)
	form.Add("projectName", ifclient.ProjectName)
	form.Add("systemName", ifclient.SystemName)

	checkProjectResponse := ifresponse.CheckAndAddCustomProjectResponse{}
	err := requests.URL(ifclient.Endpoint).Path(PROJECT_API).Params(form).Header("Content-Type", "application/x-www-form-urlencoded").ToJSON(&checkProjectResponse).Post().Fetch(context.Background())
	if err != nil {
		slog.Error("Error checking project", err)
	} else {
		if checkProjectResponse.IsSuccess {
			if checkProjectResponse.IsProjectExist {
				slog.Info(fmt.Sprintf("Project '%s' exists in the InsightFinder.", ifclient.ProjectName))
				return true
			}
		} else {
			slog.Error("Error checking project", err)
			return false
		}
		return false
	}
	return false
}

func (ifclient *InsightFinder) SendLogData(timestamp int64, instanceName string, componentName string, log any) {
	logData := ifrequest.LogData{
		TimeStamp:     timestamp,
		Tag:           instanceName,
		ComponentName: componentName,
		Data:          log,
	}
	logDataPayload := ifrequest.LogDataReceivePayload{
		UserName:         ifclient.Username,
		LicenseKey:       ifclient.LicenseKey,
		ProjectName:      ifclient.ProjectName,
		LogDataList:      []ifrequest.LogData{logData},
		InsightAgentType: "LogStreaming",
		SystemName:       ifclient.SystemName,
	}
	var response string
	err := requests.URL(ifclient.Endpoint).
		Path(LOG_DATA_API).Header("agent-type", "Stream").
		Header("Content-Type", "application/json").
		BodyJSON(logDataPayload).Post().
		ToString(&response).
		Fetch(context.Background())
	if err != nil {
		slog.Error("Error sending log data:", err)
	}
	slog.Debug(response)
}
