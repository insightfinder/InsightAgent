package tools

import "kubernetes-agent/jaeger"

func ProcessDependencyData(dependencyData *[]jaeger.DependencyData, OTMapping *map[string]string, instanceNameMapper *InstanceMapper, postProcessor *PostProcessor) *[]map[string]string {
	var result []map[string]string
	for _, dependency := range *dependencyData {
		rawSource := dependency.Parent
		rawTarget := dependency.Child
		CausalSourceComponent := (*OTMapping)[rawTarget]
		CausalTargetComponent := (*OTMapping)[rawSource]

		// Skip if source or target is not in OTMapping
		if CausalSourceComponent == "" || CausalTargetComponent == "" {
			println("Skip: " + rawSource + " -> " + rawTarget)
			continue
		}

		result = append(result, map[string]string{
			"Source": postProcessor.ProcessComponentName(CausalSourceComponent),
			"Target": postProcessor.ProcessComponentName(CausalTargetComponent),
		})
	}
	return &result
}
