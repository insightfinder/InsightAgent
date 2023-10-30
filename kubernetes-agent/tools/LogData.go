package tools

import (
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/loki"
)

func BuildLogDataList(lokiLogData *[]loki.LokiLogData, instanceNameMapper *InstanceMapper, postProcessor *PostProcessor) *[]insightfinder.LogData {
	logDataList := make([]insightfinder.LogData, 0)

	// Build logDataList
	for _, logData := range *lokiLogData {
		instanceName, componentName := instanceNameMapper.GetInstanceMapping(logData.Namespace, logData.Pod)

		// Skip if instanceName or componentName is empty
		if instanceName == "" || componentName == "" {
			continue
		}

		instanceName = logData.Container + "_" + instanceName

		componentName = postProcessor.ProcessComponentName(componentName)
		if instanceName == "" {
			continue
		}
		logDataList = append(logDataList, insightfinder.LogData{
			TimeStamp:     logData.Timestamp.UnixMilli(),
			Tag:           instanceName,
			ComponentName: componentName,
			Data:          logData.Text,
			K8Identity: insightfinder.K8Identity{
				HostId: logData.Node,
				PodId:  logData.Pod,
			},
		})
	}

	return &logDataList
}
