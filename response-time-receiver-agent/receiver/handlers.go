package receiver

import (
	"fmt"
	"os"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/insightfinder/receiver-agent/configs"
	"github.com/insightfinder/receiver-agent/insightfinder"
	"github.com/sirupsen/logrus"
)

var (
	startTime = time.Now()
	version   = "1.0.0"
)

// SetupRoutes sets up all HTTP routes for the Fiber app
func SetupRoutes(app *fiber.App, config *configs.Config) {
	// Health check endpoint
	app.Get("/health", HealthCheckHandler)

	// Data ingestion endpoint
	app.Post("/api/v1/data", func(c *fiber.Ctx) error {
		return DataIngestionHandler(c, config)
	})

	logrus.Info("HTTP routes configured successfully")
}

// HealthCheckHandler handles health check requests
func HealthCheckHandler(c *fiber.Ctx) error {
	uptime := time.Since(startTime)

	response := HealthCheckResponse{
		Status:  "healthy",
		Version: version,
		Uptime:  uptime.String(),
	}

	return c.Status(fiber.StatusOK).JSON(response)
}

// DataIngestionHandler handles incoming data from external agents
func DataIngestionHandler(c *fiber.Ctx, config *configs.Config) error {
	logrus.Info("Received data ingestion request")

	// Log raw request body for debugging
	rawBody := c.Body()
	logrus.Debugf("Raw request body: %s", string(rawBody))

	// Parse incoming data
	var incomingData IncomingData
	if err := c.BodyParser(&incomingData); err != nil {
		logrus.Errorf("Failed to parse request body: %v", err)
		return c.Status(fiber.StatusBadRequest).JSON(APIResponse{
			Success: false,
			Message: fmt.Sprintf("Invalid request format: %v", err),
		})
	}

	// Log received data
	logrus.Infof("Received data: AgentType=%s, Environment=%s, MetricCount=%d",
		incomingData.AgentType.String(), incomingData.Environment, len(incomingData.GetMetrics()))

	// Process based on agent type
	var processedMetrics []ProcessedMetric
	var processedEnvs []string
	var err error

	switch incomingData.AgentType {
	case AgentTypeServiceNowResponse:
		processedMetrics, processedEnvs, err = ProcessServiceNowResponse(&incomingData, config)
	case AgentTypeCustom:
		processedMetrics, processedEnvs, err = ProcessCustomData(&incomingData, config)
	default:
		logrus.Errorf("Unknown agent type: %d", incomingData.AgentType)
		return c.Status(fiber.StatusBadRequest).JSON(APIResponse{
			Success: false,
			Message: fmt.Sprintf("Unknown agent type: %d", incomingData.AgentType),
		})
	}

	if err != nil {
		logrus.Errorf("Failed to process data: %v", err)
		return c.Status(fiber.StatusInternalServerError).JSON(APIResponse{
			Success: false,
			Message: fmt.Sprintf("Failed to process data: %v", err),
		})
	}

	// Send metrics to InsightFinder for each environment
	successCount := 0
	failedEnvs := []string{}

	for _, pm := range processedMetrics {
		if err := sendToInsightFinder(&pm); err != nil {
			logrus.Errorf("Failed to send metrics to InsightFinder for environment '%s': %v", pm.Environment, err)
			failedEnvs = append(failedEnvs, pm.Environment)
		} else {
			successCount++
			logrus.Infof("Successfully sent metrics to InsightFinder for environment: %s", pm.Environment)
		}
	}

	// Prepare response
	if successCount == 0 {
		return c.Status(fiber.StatusInternalServerError).JSON(APIResponse{
			Success: false,
			Message: fmt.Sprintf("Failed to send metrics to all environments: %v", failedEnvs),
		})
	}

	message := fmt.Sprintf("Successfully sent metrics to %d environment(s): %v", successCount, processedEnvs)
	if len(failedEnvs) > 0 {
		message += fmt.Sprintf(". Failed for: %v", failedEnvs)
	}

	return c.Status(fiber.StatusOK).JSON(APIResponse{
		Success: true,
		Message: message,
		Data: map[string]interface{}{
			"environments_processed": processedEnvs,
			"success_count":          successCount,
			"failed_environments":    failedEnvs,
		},
	})
}

// sendToInsightFinder sends processed metrics to InsightFinder
func sendToInsightFinder(pm *ProcessedMetric) error {
	// Create InsightFinder service
	ifService := insightfinder.NewService(pm.IFConfig)

	// Ensure project exists
	if !ifService.CreateProjectIfNotExist() {
		return fmt.Errorf("failed to create or verify InsightFinder project")
	}

	// Use instance name from config, fallback to hostname if not set
	instanceName := pm.InstanceName
	if instanceName == "" {
		var err error
		instanceName, err = os.Hostname()
		if err != nil {
			instanceName = "receiver-agent"
			logrus.Warnf("Failed to get hostname, using default: %s", instanceName)
		}
	}

	logrus.Infof("Sending metrics with instance name: %s", instanceName)

	// Send metrics to InsightFinder
	return ifService.SendMetrics(instanceName, pm.Timestamp, pm.MappedMetrics)
}
