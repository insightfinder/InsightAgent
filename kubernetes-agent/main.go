package main

import (
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/prometheus"
	"kubernetes-agent/tools"
	"log"
	"time"
)

func createPrometheusServer(config *configparser.ConfigParser) prometheus.PrometheusServer {
	prometheusEndpoint, _ := config.Get("prometheus", "endpoint")
	prometheusUser, _ := config.Get("prometheus", "user")
	prometheusPassword, _ := config.Get("prometheus", "password")
	prometheusVerifyCerts, _ := config.Get("prometheus", "verify_certs")
	prometheusCACerts, _ := config.Get("prometheus", "ca_certs")
	prometheusClientCert, _ := config.Get("prometheus", "client_cert")
	prometheusClientKey, _ := config.Get("prometheus", "client_key")

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

func main() {
	// Initialize InstanceName DB
	db := tools.InstanceNameDB{}
	db.Initialize()

	// Read configuration
	configFiles := insightfinder.GetConfigFiles("conf.d")

	// Initialize time counters
	Now := time.Now()
	Before := Now.Add(-time.Minute * 10)

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
			namespaceFilter, _ := configFile.Get("prometheus", "namespace")

			// Get connection to Kubernetes
			//kubernetesConnType, _ := configFile.Get("kubernetes", "connection_type")
			//kubernetesServer := kubernetes.KubernetesServer{
			//	ConnectionType: kubernetesConnType,
			//}
			//kubernetesServer.Initialize()

			// Get all pods in the cluster
			//PodsInfo := kubernetesServer.GetPodsNodesMap()

			// Process other sections
			if IFConfig["projectType"] == "LOG" {
				log.Output(2, "TODO: Log Project")
			} else if IFConfig["projectType"] == "METRIC" {

				// Create connection to Prometheus
				prometheusServer := createPrometheusServer(configFile)
				prometheusServer.Verify()

				// Collect Data
				log.Output(2, fmt.Sprintf("Prepare to collect Prometheus data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
				metricData := make(map[string][]prometheus.PromMetricData)

				metricData["CPU"] = prometheusServer.GetMetricData("CPU", namespaceFilter, Before, Now)
				metricData["Memory"] = prometheusServer.GetMetricData("Memory", namespaceFilter, Before, Now)
				metricData["DiskRead"] = prometheusServer.GetMetricData("DiskRead", namespaceFilter, Before, Now)
				metricData["DiskWrite"] = prometheusServer.GetMetricData("DiskWrite", namespaceFilter, Before, Now)
				metricData["NetworkIn"] = prometheusServer.GetMetricData("NetworkIn", namespaceFilter, Before, Now)
				metricData["NetworkOut"] = prometheusServer.GetMetricData("NetworkOut", namespaceFilter, Before, Now)

				metricPayload := tools.BuildMetricDataPayload(&metricData, IFConfig, &db)
				tools.PrintStruct(metricPayload, false)
				insightfinder.SendMetricData(metricPayload, IFConfig)
			}
		}

		log.Output(2, "Sleep...")

		// Prepare for next 10 time range
		Before = Now
		time.Sleep(time.Minute * 10)
		Now = time.Now()
	}

}
