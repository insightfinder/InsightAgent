package receiver

import (
	"fmt"

	"github.com/insightfinder/receiver-agent/configs"
	"github.com/sirupsen/logrus"
)

// ProcessServiceNowResponse processes ServiceNow response data
// It extracts metrics, maps them using metriclistMap, and prepares data for InsightFinder
func ProcessServiceNowResponse(data *IncomingData, config *configs.Config) ([]ProcessedMetric, []string, error) {
	logrus.Infof("Processing ServiceNow response data for environment: %s", data.Environment)

	// Get metrics from either field name
	metrics := data.GetMetrics()

	// Validate incoming data
	if len(metrics) == 0 {
		return nil, nil, fmt.Errorf("no metrics provided in the request")
	}

	// Determine which environments to send to
	targetEnvs := determineTargetEnvironments(data.Environment, config)
	if len(targetEnvs) == 0 {
		return nil, nil, fmt.Errorf("no valid target environments found for: %s", data.Environment)
	}

	// Process metrics for each target environment
	var allProcessedMetrics []ProcessedMetric
	var processedEnvs []string

	for envName, envSettings := range targetEnvs {
		logrus.Infof("Processing metrics for environment: %s", envName)

		// Map incoming metrics to InsightFinder metrics using metriclistMap
		mappedMetrics := mapMetricsToInsightFinder(metrics, envSettings.MetricListMap)

		if len(mappedMetrics) == 0 {
			logrus.Warnf("No metrics matched for environment: %s", envName)
			continue
		}

		// Create processed metric for this environment
		processedMetric := ProcessedMetric{
			Environment:   envName,
			InstanceName:  envSettings.InstanceName,
			Timestamp:     int64(data.Timestamp),
			IFConfig:      envSettings.InsightFinder,
			MappedMetrics: mappedMetrics,
		}

		allProcessedMetrics = append(allProcessedMetrics, processedMetric)
		processedEnvs = append(processedEnvs, envName)

		logrus.Infof("Mapped %d metrics for environment: %s", len(mappedMetrics), envName)
	}

	if len(allProcessedMetrics) == 0 {
		return nil, nil, fmt.Errorf("no metrics were successfully mapped for any environment")
	}

	return allProcessedMetrics, processedEnvs, nil
}

// ProcessCustomData is a placeholder for custom agent data processing
func ProcessCustomData(data *IncomingData, config *configs.Config) ([]ProcessedMetric, []string, error) {
	logrus.Warnf("Custom agent processing not yet implemented")
	// TODO: Implement custom agent processing logic
	return nil, nil, fmt.Errorf("custom agent processing not yet implemented")
}

// ProcessedMetric represents a metric that has been processed and ready for InsightFinder
type ProcessedMetric struct {
	Environment   string
	InstanceName  string
	Timestamp     int64
	IFConfig      configs.InsightFinderConfig
	MappedMetrics map[string]float64 // Mapped metric name -> value
}

// determineTargetEnvironments determines which environments to send data to
func determineTargetEnvironments(requestedEnv string, config *configs.Config) map[string]*configs.EnvironmentSettings {
	targetEnvs := make(map[string]*configs.EnvironmentSettings)

	// If send_to_all_environments is true and no specific environment is requested
	if config.Environment.SendToAllEnvironments && requestedEnv == "" {
		logrus.Info("Sending to all configured environments")
		return config.Environment.GetAllEnvironments()
	}

	// If a specific environment is requested, send to all instances of that environment
	if requestedEnv != "" {
		envInstances := config.Environment.GetEnvironmentInstances(requestedEnv)
		if len(envInstances) > 0 {
			// Send to all instances of the requested environment
			for i := range envInstances {
				key := requestedEnv
				if len(envInstances) > 1 {
					key = fmt.Sprintf("%s-%d", requestedEnv, i+1)
				}
				targetEnvs[key] = &envInstances[i]
			}
			logrus.Infof("Sending to %d instance(s) of environment: %s", len(envInstances), requestedEnv)
		} else {
			logrus.Warnf("Requested environment '%s' not found in configuration", requestedEnv)
		}
	}

	return targetEnvs
}

// mapMetricsToInsightFinder maps incoming metrics to InsightFinder metric names
// and converts values from seconds to milliseconds
func mapMetricsToInsightFinder(incomingMetrics []MetricItem, metricListMap map[string]string) map[string]float64 {
	mappedMetrics := make(map[string]float64)

	for _, metric := range incomingMetrics {
		// Get metric name (supports both 'name' and 'metricName' fields)
		metricName := metric.GetName()

		// Check if this metric name exists in the metriclistMap
		if mappedName, exists := metricListMap[metricName]; exists {
			// Convert seconds to milliseconds (multiply by 1000)
			valueInMs := float64(metric.Value) * 1000
			mappedMetrics[mappedName] = valueInMs
			logrus.Debugf("Mapped metric: %s -> %s = %.2f seconds (%.2f ms)", metricName, mappedName, float64(metric.Value), valueInMs)
		} else {
			logrus.Debugf("Metric '%s' not found in metriclistMap, skipping", metricName)
		}
	}

	return mappedMetrics
}
