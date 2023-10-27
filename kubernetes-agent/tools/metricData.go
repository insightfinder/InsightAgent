package tools

import (
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/prometheus"
)

func BuildMetricDataPayload(metricDataMap *map[string][]prometheus.PromMetricData, IFConfig map[string]interface{}, instanceNameMapper *InstanceMapper, PVCPodsMapping *map[string]string, postProcessor *PostProcessor) *insightfinder.MetricDataReceivePayload {

	InsightAgentType := insightfinder.ProjectTypeToAgentType(IFConfig["projectType"].(string), false, ToBool(IFConfig["isContainer"]))
	CloudType := IFConfig["cloudType"].(string)

	// Build InstanceDataMap
	instanceDataMap := make(map[string]insightfinder.InstanceData)
	for metricType, metricData := range *metricDataMap {
		for _, promMetricData := range metricData {
			var instanceName string
			var componentName string
			if promMetricData.Pod == "" && promMetricData.NameSpace == "" {
				// Node level metric
				instanceName = promMetricData.Node
				componentName = promMetricData.Node
			} else if promMetricData.NameSpace != "" && promMetricData.PVC != "" {
				// PVC level metric
				instanceName = promMetricData.PVC

				// Use parent Deployment/StatefulSet name for component name for PVC
				if Pod, ok := (*PVCPodsMapping)[promMetricData.PVC]; ok {
					componentName = removePodNameSuffix((*PVCPodsMapping)[promMetricData.PVC])

				} else {
					componentName = removePVCNameSuffix(Pod)
				}

			} else {
				// Pod level metric
				instanceName, componentName = instanceNameMapper.GetInstanceMapping(promMetricData.NameSpace, promMetricData.Pod)
				if promMetricData.Container != "" {
					instanceName = promMetricData.Container + "_" + instanceName
				}
			}

			// Post process for component name
			componentName = postProcessor.ProcessComponentName(componentName)

			if instanceName == "" {
				continue
			}
			if _, ok := instanceDataMap[instanceName]; !ok {
				instanceDataMap[instanceName] = insightfinder.InstanceData{
					InstanceName:       instanceName,
					ComponentName:      componentName,
					DataInTimestampMap: make(map[int64]insightfinder.DataInTimestamp),
				}
			}
			dataInTimestampMap := instanceDataMap[instanceName].DataInTimestampMap

			for _, promMetricPoint := range promMetricData.Data {
				if _, ok := dataInTimestampMap[promMetricPoint.TimeStamp]; !ok {

					dataInTimestampMap[promMetricPoint.TimeStamp] = insightfinder.DataInTimestamp{
						TimeStamp:        promMetricPoint.TimeStamp,
						MetricDataPoints: make([]insightfinder.MetricDataPoint, 0),
						K8Identity: insightfinder.K8Identity{
							HostId: promMetricData.Node,
							PodId:  promMetricData.Pod,
						},
					}
				}
				dataInTimestampEntry, _ := dataInTimestampMap[promMetricPoint.TimeStamp]
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
