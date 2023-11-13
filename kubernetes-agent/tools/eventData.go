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
		if event.Regarding.Kind == "Pod" {
			instanceName, componentName = instanceNameMapper.GetInstanceMapping(event.Regarding.Namespace, event.Regarding.Name)
			componentName = postProcessor.ProcessComponentName(componentName)

		} else if event.Regarding.Kind == "StatefulSet" || event.Regarding.Kind == "ReplicaSet" {
			componentName = removePodNameSuffix(event.Regarding.Name)
			componentName = postProcessor.ProcessComponentName(event.Regarding.Name)
			instanceName = componentName
		} else if event.Regarding.Kind == "Deployment" || event.Regarding.Kind == "" {
			componentName = event.Regarding.Name
			componentName = postProcessor.ProcessComponentName(event.Regarding.Name)
			instanceName = componentName
		} else {
			instanceName = event.Regarding.Kind + "/" + event.Regarding.Name
			componentName = instanceName
		}

		// Skip empty instanceName
		if instanceName == "" {
			continue
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
