package worker

import (
	ConfigService "grafana-agent/service/config"
	"grafana-agent/service/insightfinder"
	ifrequest "grafana-agent/service/insightfinder/models/request"
	"log/slog"
	"strconv"
	"time"
)

import DbService "grafana-agent/service/db"
import GrafanaService "grafana-agent/service/grafana"

type Worker struct {
	QueryConfig    *map[string]ConfigService.QueryConfig
	ProjectConfig  *ConfigService.ProjectConfig
	DbService      *DbService.DbService
	GrafanaService *GrafanaService.GrafanaService
	InsightFinder  *insightfinder.InsightFinder
}

func CreateWorker(projectConfig *ConfigService.ProjectConfig, ifConfig *ConfigService.InsightFinderConfig, queryConfig *map[string]ConfigService.QueryConfig, grafanaService *GrafanaService.GrafanaService, dbService *DbService.DbService) *Worker {

	ifSvc := insightfinder.NewInsightFinder(ifConfig.URL, ifConfig.UserName, ifConfig.LicenseKey, projectConfig.Name, "Metric", projectConfig.System)

	// Parse Sampling Interval
	SamplingIntervalDuration, _ := time.ParseDuration(ifConfig.SamplingInterval)
	ifSvc.SamplingInterval = uint(SamplingIntervalDuration.Seconds())

	return &Worker{
		ProjectConfig:  projectConfig,
		QueryConfig:    queryConfig,
		DbService:      dbService,
		GrafanaService: grafanaService,
		InsightFinder:  &ifSvc,
	}
}

func (worker *Worker) Run(startTime time.Time, endTime time.Time) {

	worker.DbService.CreateTable(worker.ProjectConfig.Name)
	worker.InsightFinder.CreateProjectIfNotExist()

	slog.Info("WORKER", "Start Collecting Metrics for Project: ", worker.ProjectConfig.Name, "from ", startTime, " to ", endTime)

	for _, query := range worker.ProjectConfig.Query {
		queryConfig := (*worker.QueryConfig)[query]

		// Parse Sampling Interval
		SamplingInterval, _ := time.ParseDuration(strconv.Itoa(int(worker.InsightFinder.SamplingInterval)) + "s")

		// Query Grafana
		queryResponse := worker.GrafanaService.QueryData(queryConfig.Query, startTime, endTime, SamplingInterval)

		// Extract Data
		for _, frame := range queryResponse.Results.A.Frames {
			timestampList := frame.Data.Values[0]
			metricValueList := frame.Data.Values[1]

			// Process Metric Name
			var metricName string
			if queryConfig.UseRawMetricName {
				metricName = frame.Schema.Fields[1].Name
			} else {
				metricName = queryConfig.MetricName
			}

			var container, instance string
			instance = ExtractFirstAvailLabel(&queryConfig.InstanceLabel, &frame.Schema.Fields[1].Labels)

			if instance == "" {
				slog.Debug("Instance not found in metric data.", query, queryConfig.InstanceLabel)
				continue
			}

			if worker.ProjectConfig.IsContainer {
				container = ExtractFirstAvailLabel(&queryConfig.ContainerLabel, &frame.Schema.Fields[1].Labels)
				if container == "" {
					continue
				}
			} else {
				container = ""
			}
			component := ExtractFirstAvailLabel(&queryConfig.ComponentLabel, &frame.Schema.Fields[1].Labels)

			for i := range timestampList {
				timestamp := time.UnixMilli(int64(timestampList[i]))
				metricValue := metricValueList[i]
				// Save to DB
				err := worker.DbService.SaveMetrics(worker.ProjectConfig.Name, timestamp, instance, container, component, metricName, metricValue)
				if err != nil {
					slog.Error("Error saving metric data to DB", err)
				}
			}
		}
	}

	idm := make(map[string]ifrequest.InstanceData)
	// Get all Instances
	instanceContainerList := worker.DbService.GetUniqueInstances(worker.ProjectConfig.Name)
	for _, instanceContainer := range *instanceContainerList {
		instance := instanceContainer.Instance
		container := instanceContainer.Container
		var instanceName string

		if container == "" {
			instanceName = instance
		} else {
			instanceName = container + "_" + instance
		}

		// Create dit
		dit := make(map[int64]ifrequest.DataInTimestamp)

		// Get all data for this instance
		timestampList := worker.DbService.GetUniqueTimestamps(worker.ProjectConfig.Name, instance, container)
		for _, timestamp := range *timestampList {
			// Get all metrics data for this timestamp
			metricsData := worker.DbService.GetMetrics(worker.ProjectConfig.Name, timestamp, instance, container)
			metricDataPoints := make([]ifrequest.MetricDataPoint, 0)
			for _, metricData := range *metricsData {
				metricDataPoints = append(metricDataPoints, ifrequest.MetricDataPoint{
					MetricName: metricData.MetricName,
					Value:      metricData.MetricValue,
				})
			}
			dit[timestamp.UnixMilli()] = ifrequest.DataInTimestamp{
				TimeStamp:        timestamp.UnixMilli(),
				MetricDataPoints: &metricDataPoints,
			}

			idm[instanceName] = ifrequest.InstanceData{
				InstanceName:       instanceName,
				ComponentName:      worker.DbService.GetComponentName(worker.ProjectConfig.Name, instance, container),
				DataInTimestampMap: dit,
			}
		}
	}

	// Build Metrics Data to send
	metricDataPayload := ifrequest.MetricDataReceivePayload{
		ProjectName:     worker.ProjectConfig.Name,
		UserName:        worker.InsightFinder.Username,
		InstanceDataMap: idm,
		SystemName:      worker.ProjectConfig.System,
	}

	worker.InsightFinder.SendMetricData(&metricDataPayload)
	slog.Info("WORKER", "Finished Collecting Metrics for Project: ", worker.ProjectConfig.Name, "from ", startTime, " to ", endTime)

}
