package tools

import (
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/kubernetes"
)

func BuildEventsPayload(events *[]kubernetes.EventEntity, instanceNameMapper *InstanceMapper, postProcessor *PostProcessor) *[]insightfinder.LogData {
	eventDataList := make([]insightfinder.LogData, 0)

	// Build logDataList
	for _, event := range *events {
		instanceName, componentName := instanceNameMapper.GetInstanceMapping(event.Namespace, event.Regarding.Name)
		if instanceName == "" || componentName == "" {
			defaultName := event.Regarding.Kind + "/" + event.Regarding.Name
			instanceName = defaultName
			componentName = defaultName
		}
		componentName = postProcessor.ProcessComponentName(componentName)

		eventDataList = append(eventDataList, insightfinder.LogData{
			TimeStamp:     event.Time.UnixMilli(),
			Tag:           instanceName,
			ComponentName: componentName,
			Data:          event,
		})
	}

	return &eventDataList
}
