package insightfinder

import (
	"context"
	"fmt"
	"github.com/carlmjohnson/requests"
	ifresponseBody "if-jaeger-agent/insightfinder/models/response"
	"log/slog"
	"net/url"
)

const PROJECT_ENDPOINT = "/api/v1/check-and-add-custom-project"

type InsightFinder struct {
	Endpoint    string
	Username    string
	LicenseKey  string
	ProjectName string
	SystemName  string
}

func NewInsightFinder(endpoint string, username string, licenseKey string, projectName string, systemName string) InsightFinder {
	return InsightFinder{Endpoint: endpoint, Username: username, LicenseKey: licenseKey, ProjectName: projectName, SystemName: systemName}
}

func (ifclient *InsightFinder) CreateProjectIfNotExist() bool {
	// Check if the project exists
	slog.Info(fmt.Sprintf("Check if the project '%s' exists in the InsightFinder.", ifclient.ProjectName))

	form := url.Values{}
	form.Add("operation", "check")
	form.Add("userName", ifclient.Username)
	form.Add("licenseKey", ifclient.LicenseKey)
	form.Add("projectName", ifclient.ProjectName)
	form.Add("systemName", ifclient.SystemName)

	checkProjectResponse := ifresponseBody.CheckProjectResponse{}
	err := requests.URL(ifclient.Endpoint).Path(PROJECT_ENDPOINT).Params(form).Header("Content-Type", "application/x-www-form-urlencoded").ToJSON(&checkProjectResponse).Post().Fetch(context.Background())
	if err != nil {
		slog.Error("Error checking project", err)
	} else {
		if checkProjectResponse.IsSuccess {
			slog.Info(fmt.Sprintf("Project '%s' exists in the InsightFinder.", ifclient.ProjectName))
		} else {
			slog.Info(fmt.Sprintf("Project '%s' does not exist in the InsightFinder.", ifclient.ProjectName))
		}
		return checkProjectResponse.IsSuccess
	}
	return false
}
