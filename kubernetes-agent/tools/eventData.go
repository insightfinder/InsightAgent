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
			if instanceName == "" {
				continue
			}

			componentName = postProcessor.ProcessComponentName(componentName)

			if event.Regarding.Container != "" {
				instanceName = event.Regarding.Container + "_" + instanceName
			}
		} else {
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
