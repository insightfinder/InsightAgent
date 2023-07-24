package main

import (
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
				metricData := make(map[string][]prometheus.PromMetricData)

				Now := time.Now()
				TenMinBefore := Now.Add(-time.Minute * 10)

				metricData["CPU"] = prometheusServer.GetMetricData("CPU", namespaceFilter, TenMinBefore, Now)
				metricData["Memory"] = prometheusServer.GetMetricData("Memory", namespaceFilter, TenMinBefore, Now)
				metricData["DiskRead"] = prometheusServer.GetMetricData("DiskRead", namespaceFilter, TenMinBefore, Now)
				metricData["DiskWrite"] = prometheusServer.GetMetricData("DiskWrite", namespaceFilter, TenMinBefore, Now)
				metricData["NetworkIn"] = prometheusServer.GetMetricData("NetworkIn", namespaceFilter, TenMinBefore, Now)
				metricData["NetworkOut"] = prometheusServer.GetMetricData("NetworkOut", namespaceFilter, TenMinBefore, Now)

				metricPayload := tools.BuildMetricDataPayload(&metricData, IFConfig, &db)
				tools.PrintStruct(metricPayload, false)
				insightfinder.SendMetricData(metricPayload, IFConfig)
			}
		}

		log.Output(2, "Sleep...")
		time.Sleep(time.Minute * 10)
	}

}
