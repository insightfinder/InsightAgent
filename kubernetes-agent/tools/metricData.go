package tools

import (
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/prometheus"
)

func BuildMetricDataPayload(metricDataMap *map[string][]prometheus.PromMetricData, IFConfig map[string]interface{}, instanceNameMapper *InstanceMapper) insightfinder.MetricDataReceivePayload {

	// Build InstanceDataMap
	instanceDataMap := make(map[string]insightfinder.InstanceData)
	for _, metricData := range *metricDataMap {
		for _, promMetricData := range metricData {
			instanceName := instanceNameMapper.GetInstanceName(promMetricData.NameSpace, promMetricData.Pod)
			if instanceName == "" {
				continue
			}
			if _, ok := instanceDataMap[instanceName]; !ok {
				instanceDataMap[instanceName] = insightfinder.InstanceData{
					InstanceName:       instanceName,
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
					MetricName: promMetricData.Type,
					Value:      promMetricPoint.Value,
				})
				dataInTimestampMap[promMetricPoint.TimeStamp] = dataInTimestampEntry
			}
		}

	}
	return insightfinder.MetricDataReceivePayload{
		ProjectName:      IFConfig["projectName"].(string),
		UserName:         IFConfig["userName"].(string),
		InstanceDataMap:  instanceDataMap,
		SystemName:       IFConfig["systemName"].(string),
		MinTimestamp:     0,
		MaxTimestamp:     0,
		InsightAgentType: insightfinder.ProjectTypeToAgentType(IFConfig["projectType"].(string), false),
	}
}

func buildNamespacePodMap(promMetricDataList []prometheus.PromMetricData) *map[string]bool {
	namespacePodMap := make(map[string]bool)
	for _, promMetricData := range promMetricDataList {
		namespacePodMap[promMetricData.NameSpace+"/"+promMetricData.Pod] = true
	}
	return &namespacePodMap
}
