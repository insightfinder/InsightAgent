package main

import (
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"kubernetes-agent/host_mapper"
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/jaeger"
	"kubernetes-agent/kubernetes"
	"kubernetes-agent/loki"
	"kubernetes-agent/prometheus"
	"kubernetes-agent/tools"
	"log"
	"time"
)

const GENERAL_SECTION = "general"
const PROMETHEUS_SECTION = "prometheus"
const LOKI_SECTION = "loki"
const JAEGER_SECTION = "jaeger"

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
	lokiUsername, _ := config.Get(LOKI_SECTION, "user")
	lokiPassword, _ := config.Get(LOKI_SECTION, "password")
	return loki.LokiServer{Endpoint: lokiEndpoint, Username: lokiUsername, Password: lokiPassword}
}

func createJaegerServer(config *configparser.ConfigParser) jaeger.Jaeger {
	jaegerEndpoint, _ := config.Get(JAEGER_SECTION, "endpoint")
	jaegerUsername, _ := config.Get(JAEGER_SECTION, "user")
	jaegerPassword, _ := config.Get(JAEGER_SECTION, "password")
	return jaeger.Jaeger{Endpoint: jaegerEndpoint, Username: jaegerUsername, Password: jaegerPassword}
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

	// Initialize Kubernetes Server
	kubernetesServer := kubernetes.KubernetesServer{}
	kubernetesServer.Initialize()

	// Initialize InstanceName DB
	instanceMapper := tools.InstanceMapper{}
	instanceMapper.Initialize(&kubernetesServer)
	for _, configFile := range configFiles {
		// Add Namespaces from all config files
		namespaceFilter, _ := configFile.Get(GENERAL_SECTION, "namespace")
		collectionTarget, _ := configFile.Get(GENERAL_SECTION, "target")
		if namespaceFilter != "" && collectionTarget != "node" && collectionTarget != "pvc" {
			instanceMapper.AddNamespace(namespaceFilter)
		}
	}

	// Initialize HostMapper DB
	hostMapper := host_mapper.HostMapper{}
	hostMapper.Initialize(&kubernetesServer)

	// Start data collection routine
	EndTime := time.Now()
	StartTime := EndTime.Add(-time.Second * 10)
	for {
		log.Output(2, "Start...")

		// Process Pod Instance mapping during each run.
		instanceMapper.Update()

		// Process Host mapping during each run.
		hostMapper.Update()

		// Process data collection based each config file
		for _, configFile := range configFiles {
			go dataCollectionRoutine(configFile, &kubernetesServer, &instanceMapper, &hostMapper, StartTime, EndTime)
		}

		// Prepare for next 10 seconds time range
		StartTime = EndTime
		time.Sleep(time.Second * 10)
		EndTime = time.Now()
	}
}

func dataCollectionRoutine(configFile *configparser.ConfigParser, kubernetesServer *kubernetes.KubernetesServer, instanceMapper *tools.InstanceMapper, hostMapper *host_mapper.HostMapper, Before time.Time, Now time.Time) {

	// Get InsightFinder config
	IFConfig := insightfinder.GetInsightFinderConfig(configFile)
	insightfinder.CheckProject(IFConfig)

	// Get General config
	namespaceFilter, _ := configFile.Get(GENERAL_SECTION, "namespace")
	collectionTarget, _ := configFile.Get(GENERAL_SECTION, "target")
	collectionType, _ := configFile.Get(GENERAL_SECTION, "type")
	postProcessor := tools.PostProcessor{}
	postProcessor.Initialize(configFile)

	// Process other sections
	if collectionType == "log" {
		// Create connection to Loki
		lokiServer := createLokiServer(configFile)
		lokiServer.Initialize()

		// Collect Data
		log.Output(2, fmt.Sprintf("Prepare to collect log data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))

		if collectionTarget == "node" {
			log.Output(2, "TODO: Collecting log data from node.")
		} else {
			podList := instanceMapper.ListPods(namespaceFilter)
			logData := lokiServer.GetLogData(namespaceFilter, podList, Before, Now)
			log.Output(2, fmt.Sprintf("Finished collecting log data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))

			// Send data
			logDataList := tools.BuildLogDataList(&logData, instanceMapper, &postProcessor)
			tools.PrintStruct(*logDataList, false, IFConfig["projectName"].(string))
			log.Output(2, fmt.Sprintf("Start sending log data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
			insightfinder.SendLogData(logDataList, IFConfig)
			log.Output(2, "Finished sending log data.")
		}

	} else if collectionType == "metric" {

		// Create connection to Prometheus
		prometheusServer := createPrometheusServer(configFile)
		prometheusServer.Initialize()

		// Collect Data
		log.Output(2, fmt.Sprintf("Prepare to collect metric data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		metricData := make(map[string][]prometheus.PromMetricData)
		PVCMetricData := make(map[string][]prometheus.PromMetricData)

		if collectionTarget == "node" {
			metricData["CPU"] = prometheusServer.GetMetricData("NodeCPU", "", Before, Now)
			metricData["Memory"] = prometheusServer.GetMetricData("NodeMemory", "", Before, Now)
			metricData["MemoryUsage"] = prometheusServer.GetMetricData("NodeMemoryUsage", "", Before, Now)
			metricData["DiskUsage"] = prometheusServer.GetMetricData("NodeDiskUsage", "", Before, Now)
			metricData["DiskRead"] = prometheusServer.GetMetricData("NodeDiskRead", "", Before, Now)
			metricData["DiskWrite"] = prometheusServer.GetMetricData("NodeDiskWrite", "", Before, Now)
			metricData["NetworkIn"] = prometheusServer.GetMetricData("NodeNetworkIn", "", Before, Now)
			metricData["NetworkOut"] = prometheusServer.GetMetricData("NodeNetworkOut", "", Before, Now)
			metricData["Processes"] = prometheusServer.GetMetricData("NodeProcesses", "", Before, Now)
			metricData["BlockedProcesses"] = prometheusServer.GetMetricData("NodeBlockedProcesses", "", Before, Now)
		} else if collectionTarget == "pvc" {
			log.Output(2, "Skip: Collecting metric data from PVC.")
		} else {
			metricData["CPUCores"] = prometheusServer.GetMetricData("PodCPUCores", namespaceFilter, Before, Now)
			metricData["CPU"] = prometheusServer.GetMetricData("PodCPUUsage", namespaceFilter, Before, Now)
			metricData["Memory"] = prometheusServer.GetMetricData("PodMemory", namespaceFilter, Before, Now)
			metricData["MemoryUsage"] = prometheusServer.GetMetricData("PodMemoryUsage", namespaceFilter, Before, Now)
			metricData["MemoryRequestUsage"] = prometheusServer.GetMetricData("PodRequestMemoryUsage", namespaceFilter, Before, Now)
			metricData["MemoryRequests"] = prometheusServer.GetMetricData("PodMemoryRequests", namespaceFilter, Before, Now)
			metricData["MemoryLimits"] = prometheusServer.GetMetricData("PodMemoryLimits", namespaceFilter, Before, Now)
			metricData["DiskRead"] = prometheusServer.GetMetricData("PodDiskRead", namespaceFilter, Before, Now)
			metricData["DiskWrite"] = prometheusServer.GetMetricData("PodDiskWrite", namespaceFilter, Before, Now)
			metricData["NetworkIn"] = prometheusServer.GetMetricData("PodNetworkIn", namespaceFilter, Before, Now)
			metricData["NetworkOut"] = prometheusServer.GetMetricData("PodNetworkOut", namespaceFilter, Before, Now)
			metricData["Processes"] = prometheusServer.GetMetricData("PodProcesses", namespaceFilter, Before, Now)
			metricData["RestartCount"] = prometheusServer.GetMetricData("PodContainerRestart", namespaceFilter, Before, Now)

			// Collect PVC Metrics and append to Pods
			PVCMetricData["Capacity"] = prometheusServer.GetMetricData("PVCCapacity", namespaceFilter, Before, Now)
			PVCMetricData["Used"] = prometheusServer.GetMetricData("PVCUsed", namespaceFilter, Before, Now)
			PVCMetricData["Usage"] = prometheusServer.GetMetricData("PVCUsage", namespaceFilter, Before, Now)
			PodPVCMapping := kubernetesServer.GetPodsPVCMapping(namespaceFilter)
			tools.MergePVCMetricsToPodMetrics(&PVCMetricData, &metricData, PodPVCMapping)

		}
		log.Output(2, fmt.Sprintf("Finished collecting metric data from %s to %s", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))

		metricPayload := tools.BuildMetricDataPayload(&metricData, IFConfig, instanceMapper, hostMapper, &postProcessor)
		tools.PrintStruct(*metricPayload, false, IFConfig["projectName"].(string))
		log.Output(2, fmt.Sprintf("Start sending metic data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		insightfinder.SendMetricData(metricPayload, IFConfig)
		log.Output(2, "Finished sending metric data.")
	} else if collectionType == "event" {
		// Collect normal events
		generalEvents := kubernetesServer.GetEvents(namespaceFilter, Before, Now)
		generalEventPayload := tools.BuildEventsPayload(generalEvents, instanceMapper, &postProcessor)
		tools.PrintStruct(*generalEventPayload, false, IFConfig["projectName"].(string)+"-general")

		// Collect Pod Container Exit Events
		containerExitEvents := kubernetesServer.GetPodsContainerExitEvents(namespaceFilter, Before, Now)
		containerExitEventPayload := tools.BuildEventsPayload(containerExitEvents, instanceMapper, &postProcessor)
		tools.PrintStruct(*containerExitEventPayload, false, IFConfig["projectName"].(string)+"-containerExit")

		log.Output(2, fmt.Sprintf("Start sending event data from %s to %s.", Before.Format(time.RFC3339), Now.Format(time.RFC3339)))
		insightfinder.SendLogData(generalEventPayload, IFConfig)
		insightfinder.SendLogData(containerExitEventPayload, IFConfig)
		log.Output(2, "Finished sending event data.")

	} else if collectionType == "trace" {
		// Collect Dependency Graph
		jaegerServer := createJaegerServer(configFile)
		DAG := jaegerServer.GetDAG()
		OTMapping := kubernetesServer.GetOpenTelemetryMapping(namespaceFilter)
		dependencyMap := tools.ProcessDependencyData(DAG, OTMapping, instanceMapper, &postProcessor)
		insightfinder.SendDependencyMap(dependencyMap, IFConfig)
	} else {
		log.Output(2, "Unknown collection type.")
	}
}
