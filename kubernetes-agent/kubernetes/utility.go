package kubernetes

import "strings"

func getPodNameFromEventMessage(message string) string {
	splitResult := strings.Split(message, ":")
	return strings.ReplaceAll(splitResult[len(splitResult)-1], " ", "")
}

func findPodInEvents(podName string, resourceKind string, resource string, events *map[string]map[string]map[string]bool) bool {
	if (*events)[resourceKind] == nil {
		return false
	}
	if (*events)[resourceKind][resource] == nil {
		return false
	}

	pods := (*events)[resourceKind][resource]
	if _, found := pods[podName]; found {
		return true
	}

	return false
}
