package tools

import (
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/kubernetes"
)

func BuildEventsPayload(events *[]kubernetes.EventEntity, instanceNameMapper *InstanceMapper, postProcessor *PostProcessor) *[]insightfinder.LogData {
	eventDataList := make([]insightfinder.LogData, 0)

	// Build logDataList
	for _, event := range *events {
		var instanceName, componentName string
		if event.Regarding.Kind == "Pod" || event.Regarding.Kind == "ReplicaSet" {
			componentName = removePodNameSuffix(event.Regarding.Name)
			componentName = postProcessor.ProcessComponentName(componentName)
			instanceName = componentName
		} else {
			instanceName = event.Regarding.Kind + "/" + event.Regarding.Name
			componentName = instanceName
		}

		eventDataList = append(eventDataList, insightfinder.LogData{
			TimeStamp:     event.Time.UnixMilli(),
			Tag:           instanceName,
			ComponentName: componentName,
			Data:          event,
		})
	}

	return &eventDataList
}
