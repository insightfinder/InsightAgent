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
	// Initialize InstanceName DB
	instanceMapper := tools.InstanceMapper{}
	instanceMapper.Initialize()

	// Read configuration
	configFiles := insightfinder.GetConfigFiles("conf.d")

	// Initialize time counters
	Now := time.Now()
	Before := Now.Add(-time.Minute * 1)

	for {
		log.Output(2, "Start...")

		for _, configFilePath := range configFiles {
			// Open the ini config file
			configFile, err := configparser.NewConfigParserFromFile(configFilePath)
			if err != nil {
				println(err)
				return
			}
			// Get InsightFinder config
			IFConfig := insightfinder.GetInsightFinderConfig(configFile)
			insightfinder.CheckProject(IFConfig)

			// Get Namespace need to use
			namespaceFilter, _ := configFile.Get("general", "namespace")
			instanceMapper.AddNamespace(namespaceFilter)
			instanceMapper.Update()

			// Process other sections
			if IFConfig["projectType"] == "LOG" {
				// Create connection to Loki
				lokiServer := createLokiServer(configFile)
				lokiServer.Initialize()

				// Collect Data
				log.Output(2, fmt.Sprintf("Prepare to collect Loki data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
				podList := instanceMapper.ListPods(namespaceFilter)
				logData := lokiServer.GetLogData(namespaceFilter, podList, Before, Now)

				// Send data
				logDataList := tools.BuildLogDataList(&logData, &instanceMapper)
				//tools.PrintStruct(logDataList, false)
				log.Output(2, fmt.Sprintf("Start sending log data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
				insightfinder.SendLogData(logDataList, IFConfig)

			} else if IFConfig["projectType"] == "METRIC" {

				// Create connection to Prometheus
				prometheusServer := createPrometheusServer(configFile)
				prometheusServer.Initialize()

				// Collect Data
				log.Output(2, fmt.Sprintf("Prepare to collect Prometheus data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
				metricData := make(map[string][]prometheus.PromMetricData)

				metricData["CPU"] = prometheusServer.GetMetricData("CPU", namespaceFilter, Before, Now)
				metricData["Memory"] = prometheusServer.GetMetricData("Memory", namespaceFilter, Before, Now)
				metricData["DiskRead"] = prometheusServer.GetMetricData("DiskRead", namespaceFilter, Before, Now)
				metricData["DiskWrite"] = prometheusServer.GetMetricData("DiskWrite", namespaceFilter, Before, Now)
				metricData["NetworkIn"] = prometheusServer.GetMetricData("NetworkIn", namespaceFilter, Before, Now)
				metricData["NetworkOut"] = prometheusServer.GetMetricData("NetworkOut", namespaceFilter, Before, Now)

				metricPayload := tools.BuildMetricDataPayload(&metricData, IFConfig, &instanceMapper)
				//tools.PrintStruct(metricPayload, false)
				log.Output(2, fmt.Sprintf("Start sending metic data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
				insightfinder.SendMetricData(metricPayload, IFConfig)
			}
		}

		log.Output(2, "Finished sending data.")

		// Prepare for next 1 time range
		Before = Now
		time.Sleep(time.Minute * 1)
		Now = time.Now()
	}

}
