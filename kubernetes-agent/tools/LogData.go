package tools

import (
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/loki"
)

func BuildLogDataList(lokiLogData *[]loki.LokiLogData, IFConfig map[string]interface{}, instanceNameMapper *InstanceMapper) []insightfinder.LogData {
	logDataList := make([]insightfinder.LogData, 0)

	// Build logDataList
	for _, logData := range *lokiLogData {
		instanceName := instanceNameMapper.GetInstanceName(logData.Namespace, logData.Pod)
		if instanceName == "" {
			continue
		}
		logDataList = append(logDataList, insightfinder.LogData{
			TimeStamp: logData.Timestamp.UnixMilli(),
			Tag:       instanceName,
			Data:      logData.Text,
		})
	}

	return logDataList
}