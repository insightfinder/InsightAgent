package main

import (
	"fmt"
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/loki"
	"kubernetes-agent/prometheus"
	"kubernetes-agent/tools"
	"log"
	"time"

	"github.com/bigkevmcd/go-configparser"
)

const PROMETHEUS_SECTION = "prometheus"
const LOKI_SECTION = "loki"

func createPrometheusServer(config *configparser.ConfigParser) prometheus.PrometheusServer {
	prometheusEndpoint, _ := config.Get(PROMETHEUS_SECTION, "endpoint")
	prometheusUser, _ := config.Get(PROMETHEUS_SECTION, "user")
	prometheusPassword, _ := config.Get(PROMETHEUS_SECTION, "password")
	prometheusVerifyCerts, _ := config.Get(PROMETHEUS_SECTION, "verify_certs")
	prometheusCACerts, _ := config.Get(PROMETHEUS_SECTION, "ca_certs")
	prometheusClientCert, _ := config.Get(PROMETHEUS_SECTION, "client_cert")
	prometheusClientKey, _ := config.Get(PROMETHEUS_SECTION, "client_key")

	return prometheus.PrometheusServer{
		EndPoint:    prometheusEndpoint,
		UserName:    prometheusUser,
		Password:    prometheusPassword,
		VerifyCerts: prometheusVerifyCerts,
		CACerts:     prometheusCACerts,
		ClientCert:  prometheusClientCert,
		ClientKey:   prometheusClientKey,
	}
}

func createLokiServer(config *configparser.ConfigParser) loki.LokiServer {
	lokiEndpoint, _ := config.Get(LOKI_SECTION, "endpoint")
	return loki.LokiServer{Endpoint: lokiEndpoint}
}

func main() {

	// Read configuration files
	configFileList := insightfinder.GetConfigFiles("conf.d")
	configFiles := make([]*configparser.ConfigParser, 0)
	for _, configFilePath := range configFileList {
		configFile, err := configparser.NewConfigParserFromFile(configFilePath)
		if err != nil {
			println(err)
			return
		}
		configFiles = append(configFiles, configFile)
	}

	// Initialize InstanceName DB
	instanceMapper := tools.InstanceMapper{}
	instanceMapper.Initialize()
	for _, configFile := range configFiles {
		// Add Namespaces from all config files
		namespaceFilter, _ := configFile.Get("general", "namespace")
		instanceMapper.AddNamespace(namespaceFilter)
	}

	// Initialize time ranges
	EndTime := time.Now()
	StartTime := EndTime.Add(-time.Second * 30)

	for {
		log.Output(2, "Start...")

		// Process Pod Instance mapping during each run.
		instanceMapper.Update()

		// Process data collection based each config file
		for _, configFile := range configFiles {
			dataCollectionRoutine(configFile, &instanceMapper, StartTime, EndTime)
		}

		// Prepare for next 30 seconds time range
		StartTime = EndTime
		time.Sleep(time.Second * 30)
		EndTime = time.Now()
	}
}

func dataCollectionRoutine(configFile *configparser.ConfigParser, instanceMapper *tools.InstanceMapper, Before time.Time, Now time.Time) {

	// Get InsightFinder config
	IFConfig := insightfinder.GetInsightFinderConfig(configFile)
	insightfinder.CheckProject(IFConfig)

	// Get Namespace need to use
	namespaceFilter, _ := configFile.Get("general", "namespace")

	// Process other sections
	if IFConfig["projectType"] == "LOG" {
		// Create connection to Loki
		lokiServer := createLokiServer(configFile)
		lokiServer.Initialize()

		// Collect Data
		log.Output(2, fmt.Sprintf("Prepare to collect log data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		podList := instanceMapper.ListPods(namespaceFilter)
		logData := lokiServer.GetLogData(namespaceFilter, podList, Before, Now)

		// Send data
		logDataList := tools.BuildLogDataList(&logData, instanceMapper)
		tools.PrintStruct(logDataList, false)
		log.Output(2, fmt.Sprintf("Start sending log data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		//insightfinder.SendLogData(logDataList, IFConfig)
		log.Output(2, "Finished sending log data.")

	} else if IFConfig["projectType"] == "METRIC" {

		// Create connection to Prometheus
		prometheusServer := createPrometheusServer(configFile)
		prometheusServer.Initialize()

		// Collect Data
		log.Output(2, fmt.Sprintf("Prepare to collect metric data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		metricData := make(map[string][]prometheus.PromMetricData)

		metricData["CPU"] = prometheusServer.GetMetricData("CPU", namespaceFilter, Before, Now)
		metricData["Memory"] = prometheusServer.GetMetricData("Memory", namespaceFilter, Before, Now)
		metricData["DiskRead"] = prometheusServer.GetMetricData("DiskRead", namespaceFilter, Before, Now)
		metricData["DiskWrite"] = prometheusServer.GetMetricData("DiskWrite", namespaceFilter, Before, Now)
		metricData["NetworkIn"] = prometheusServer.GetMetricData("NetworkIn", namespaceFilter, Before, Now)
		metricData["NetworkOut"] = prometheusServer.GetMetricData("NetworkOut", namespaceFilter, Before, Now)

		metricPayload := tools.BuildMetricDataPayload(&metricData, IFConfig, instanceMapper)
		//tools.PrintStruct(metricPayload, false)
		log.Output(2, fmt.Sprintf("Start sending metic data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		insightfinder.SendMetricData(metricPayload, IFConfig)
		log.Output(2, "Finished sending metric data.")
	}
}
