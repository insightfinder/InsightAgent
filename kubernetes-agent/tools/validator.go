package tools

import "kubernetes-agent/insightfinder"

func ValidateData(instanceDataMap map[string]insightfinder.InstanceData) {
	for _, instanceData := range instanceDataMap {
		instanceName := instanceData.InstanceName
		if len(instanceData.DataInTimestampMap) != 10 {
			println(instanceName+" has insufficient data points:", len(instanceData.DataInTimestampMap))
		}
		for TimeStamp, dataInTimestamp := range instanceData.DataInTimestampMap {

			metricType := make(map[string]bool)
			for _, metricPoint := range dataInTimestamp.MetricDataPoints {
				metricType[metricPoint.MetricName] = true
			}
			if len(metricType) != 6 {
				println(instanceName + " Miss data at " + ToString(TimeStamp))
				//PrintSet(metricType)
			}
		}
	}
}
