package tools

import (
	"github.com/bigkevmcd/go-configparser"
	"kubernetes-agent/insightfinder"
	"kubernetes-agent/kubernetes"
)

func BuildEventsPayload(events *[]kubernetes.EventEntity, postProcessor *PostProcessor) *[]insightfinder.LogData {
	eventDataList := make([]insightfinder.LogData, 0)

	// Build logDataList
	for _, event := range *events {
		var instanceName, componentName string
		if event.Regarding.Kind == "Pod" || event.Regarding.Kind == "ReplicaSet" {
			componentName = removePodNameSuffix(event.Regarding.Name)
			componentName = postProcessor.ProcessComponentName(componentName)
			instanceName = componentName
		} else if event.Regarding.Kind == "Deployment" {
			componentName = postProcessor.ProcessComponentName(event.Regarding.Name)
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

func EventDataStreamingRoutine(chn *chan *kubernetes.EventEntity, postProcessor *PostProcessor, configFile *configparser.ConfigParser) {
	IFConfig := insightfinder.GetInsightFinderConfig(configFile)
	for {
		event := <-*chn
		eventPayload := BuildEventsPayload(&[]kubernetes.EventEntity{*event}, postProcessor)
		insightfinder.SendLogData(eventPayload, IFConfig)
	}
}
