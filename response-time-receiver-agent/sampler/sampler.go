package sampler

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/insightfinder/receiver-agent/configs"
	"github.com/sirupsen/logrus"
)

// NewSamplerService creates a new sampler service
func NewSamplerService(config *configs.SamplerConfig, appConfig *configs.Config) *SamplerService {
	return &SamplerService{
		config:    config,
		appConfig: appConfig,
		stopChan:  make(chan struct{}),
	}
}

// Start begins the periodic sampling routine
func (s *SamplerService) Start() {
	if !s.config.Enabled {
		logrus.Info("Sampler is disabled, not starting")
		return
	}

	// Validate that metrics are configured
	if len(s.config.Metrics) == 0 {
		logrus.Warn("Sampler is enabled but no metrics are configured, not starting")
		return
	}

	logrus.Infof("Starting sampler service with interval: %d seconds", s.config.SamplingInterval)
	logrus.Infof("Configured metrics: %v", s.config.Metrics)

	go s.run()
}

// Stop stops the sampler service
func (s *SamplerService) Stop() {
	if !s.config.Enabled {
		return
	}

	logrus.Info("Stopping sampler service...")
	close(s.stopChan)
}

// run is the main sampling loop
func (s *SamplerService) run() {
	// Create ticker with configured interval
	ticker := time.NewTicker(time.Duration(s.config.SamplingInterval) * time.Second)
	defer ticker.Stop()

	// Send first sample immediately
	s.sendSample()

	// Continue sending samples at interval
	for {
		select {
		case <-ticker.C:
			s.sendSample()
		case <-s.stopChan:
			logrus.Info("Sampler service stopped")
			return
		}
	}
}

// sendSample sends a sample with metric value 0 to both staging and production environments
func (s *SamplerService) sendSample() {
	logrus.Debug("Sending periodic sample with metric value 0")

	environments := []string{"staging", "production"}

	for _, env := range environments {
		// Check if environment exists in config
		envInstances := s.appConfig.Environment.GetEnvironmentInstances(env)
		if len(envInstances) == 0 {
			logrus.Warnf("Environment '%s' not found in configuration, skipping", env)
			continue
		}

		// Send sample for this environment
		if err := s.sendSampleForEnvironment(env); err != nil {
			logrus.Errorf("Failed to send sample for environment '%s': %v", env, err)
		} else {
			logrus.Debugf("Successfully sent sample for environment: %s", env)
		}
	}
}

// sendSampleForEnvironment sends a sample to a specific environment
func (s *SamplerService) sendSampleForEnvironment(environment string) error {
	// Convert metrics map to metriclist array format expected by receiver
	metricList := make([]map[string]interface{}, 0, len(s.config.Metrics))
	for name, value := range s.config.Metrics {
		metricList = append(metricList, map[string]interface{}{
			"name":  name,
			"value": value,
		})
	}

	// Create payload with metric value 0
	payload := map[string]interface{}{
		"agentType":   0, // ServiceNow response type
		"environment": environment,
		"timestamp":   time.Now().UnixMilli(),
		"metriclist":  metricList, // Use metriclist format expected by receiver
	}

	// Convert to JSON
	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	logrus.Debugf("Sending payload to %s: %s", environment, string(jsonData))

	// Send HTTP POST request
	resp, err := http.Post(
		s.config.ServerURL,
		"application/json",
		bytes.NewBuffer(jsonData),
	)
	if err != nil {
		return fmt.Errorf("failed to send HTTP request: %w", err)
	}
	defer resp.Body.Close()

	// Check response status
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("received non-OK status code: %d", resp.StatusCode)
	}

	return nil
}
