package tools

import (
	"fmt"
	"kubernetes-agent/host_mapper"
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/prometheus"
	"math"
)

func BuildMetricDataPayload(metricDataMap *map[string][]prometheus.PromMetricData, IFConfig map[string]interface{}, instanceNameMapper *InstanceMapper, hostMapper *host_mapper.HostMapper, postProcessor *PostProcessor) *insightfinder.MetricDataReceivePayload {

	InsightAgentType := insightfinder.ProjectTypeToAgentType(IFConfig["projectType"].(string), false, ToBool(IFConfig["isContainer"]))
	CloudType := IFConfig["cloudType"].(string)

	// Get node mappings to their specific regions
	nodeRegionsMap := *instanceNameMapper.GetNodeRegionMapping()

	// Build InstanceDataMap
	instanceDataMap := make(map[string]insightfinder.InstanceData)
	for metricType, metricData := range *metricDataMap {
		for _, promMetricData := range metricData {
			var instanceName string
			var componentName string
			if promMetricData.Pod == "" && promMetricData.NameSpace == "" {
				// Node level metric
				var err error
				instanceName, err = hostMapper.GetHostInstanceName(promMetricData.Node)
				componentName = promMetricData.Node

				// Skip the metric data point if the host mapping is failing.
				if err != nil {
					fmt.Println(err.Error())
					continue
				}

			} else {
				// Pod level metric
				instanceName, componentName = instanceNameMapper.GetInstanceMapping(promMetricData.NameSpace, promMetricData.Pod)

				// Skip if instanceName is empty
				if instanceName == "" {
					continue
				}

				// Add container name to instance name
				if promMetricData.Container != "" {
					instanceName = promMetricData.Container + "_" + instanceName
				}
			}

			// Post process for component name
			componentName = postProcessor.ProcessComponentName(componentName)

			if instanceName == "" {
				continue
			}

			zone, ok := nodeRegionsMap[promMetricData.Node]
			if !ok {
				zone = "unknown"
			}
			if _, ok := instanceDataMap[instanceName]; !ok {
				instanceDataMap[instanceName] = insightfinder.InstanceData{
					InstanceName:       instanceName,
					ComponentName:      componentName,
					Zone:               zone,
					DataInTimestampMap: make(map[int64]insightfinder.DataInTimestamp),
				}
			}
			dataInTimestampMap := instanceDataMap[instanceName].DataInTimestampMap

			for _, promMetricPoint := range promMetricData.Data {
				if _, ok := dataInTimestampMap[promMetricPoint.TimeStamp]; !ok {

					dataInTimestampMap[promMetricPoint.TimeStamp] = insightfinder.DataInTimestamp{
						TimeStamp:        promMetricPoint.TimeStamp,
						MetricDataPoints: make([]insightfinder.MetricDataPoint, 0),
						K8Identity: &insightfinder.K8Identity{
							HostId: promMetricData.Node,
							PodId:  promMetricData.Pod,
						},
					}
				}
				dataInTimestampEntry, _ := dataInTimestampMap[promMetricPoint.TimeStamp]

				// Process Inf value.
				if promMetricPoint.Value == math.Inf(1) || promMetricPoint.Value == math.Inf(-1) {
					promMetricPoint.Value = 0
				}

				dataInTimestampEntry.MetricDataPoints = append(dataInTimestampEntry.MetricDataPoints, insightfinder.MetricDataPoint{
					MetricName: metricType,
					Value:      promMetricPoint.Value,
				})
				dataInTimestampMap[promMetricPoint.TimeStamp] = dataInTimestampEntry
			}
		}

	}

	return &insightfinder.MetricDataReceivePayload{
		ProjectName:      IFConfig["projectName"].(string),
		UserName:         IFConfig["userName"].(string),
		InstanceDataMap:  instanceDataMap,
		SystemName:       IFConfig["systemName"].(string),
		MinTimestamp:     0,
		MaxTimestamp:     0,
		InsightAgentType: InsightAgentType,
		CloudType:        CloudType,
	}
}

func MergePVCMetricsToPodMetrics(PVCMetrics *map[string][]prometheus.PromMetricData, PodMetrics *map[string][]prometheus.PromMetricData, PodPVCMapping *map[string]map[string]map[string][]string) {

	// Build PVC metrics map:PVC -> []PromMetricData
	PVCMetricsData := make(map[string][]prometheus.PromMetricData)
	for _, PVCMetricData := range *PVCMetrics {
		for _, PVCMetric := range PVCMetricData {
			PVCMetricsData[PVCMetric.PVC] = append(PVCMetricsData[PVCMetric.PVC], PVCMetric)
		}
	}

	// Merge PVC metrics to Pod metrics
	for Pod, PodPVCs := range *PodPVCMapping {
		for PVC, MountPoints := range PodPVCs {
			for MountPoint, Containers := range MountPoints {
				for _, Container := range Containers {
					for _, PVCData := range PVCMetricsData[PVC] {
						metricData := PVCData
						metricData.Pod = Pod
						metricData.Container = Container
						metricData.PVC = PVC
						metricName := PVCData.Type + "-" + MountPoint
						(*PodMetrics)[metricName] = append((*PodMetrics)[metricName], metricData)
					}
				}
			}
		}
	}
}
