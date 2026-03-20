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

// lastScheduledSend tracks the last date a scheduled entry was sent (keyed by index)
// to avoid duplicate sends within the same minute
var lastScheduledSend = map[int]string{}

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

	hasPeriodicMetrics := len(s.config.Metrics) > 0
	hasScheduledMetrics := len(s.config.ScheduledMetrics) > 0

	if !hasPeriodicMetrics && !hasScheduledMetrics {
		logrus.Warn("Sampler is enabled but no metrics or scheduled_metrics are configured, not starting")
		return
	}

	if hasPeriodicMetrics {
		logrus.Infof("Starting sampler service with interval: %d seconds", s.config.SamplingInterval)
		logrus.Infof("Configured periodic metrics: %v", s.config.Metrics)
		go s.run()
	}

	if hasScheduledMetrics {
		logrus.Infof("Starting scheduled metrics service with %d schedule(s)", len(s.config.ScheduledMetrics))
		for _, sched := range s.config.ScheduledMetrics {
			logrus.Infof("  Scheduled at %s UTC: %v", sched.Time, sched.Metrics)
		}
		go s.runScheduled()
	}
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

// runScheduled checks every minute whether any scheduled metric entry should be sent
func (s *SamplerService) runScheduled() {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()

	// Also check immediately on start in case we're right at a scheduled time
	s.checkAndSendScheduled()

	for {
		select {
		case <-ticker.C:
			s.checkAndSendScheduled()
		case <-s.stopChan:
			logrus.Info("Scheduled metrics service stopped")
			return
		}
	}
}

// checkAndSendScheduled fires any scheduled entries whose time matches the current UTC HH:MM
func (s *SamplerService) checkAndSendScheduled() {
	now := time.Now().UTC()
	currentTime := fmt.Sprintf("%02d:%02d", now.Hour(), now.Minute())
	today := now.Format("2006-01-02")

	for i, sched := range s.config.ScheduledMetrics {
		if sched.Time != currentTime {
			continue
		}
		// Guard against duplicate sends within the same minute
		if lastScheduledSend[i] == today+":"+currentTime {
			continue
		}
		lastScheduledSend[i] = today + ":" + currentTime

		logrus.Infof("Sending scheduled metrics for time %s UTC: %v", sched.Time, sched.Metrics)
		s.sendScheduledSample(sched.Metrics)
	}
}

// sendScheduledSample sends a scheduled set of metrics to all environments
func (s *SamplerService) sendScheduledSample(metrics map[string]float64) {
	environments := []string{"staging", "production"}

	for _, env := range environments {
		envInstances := s.appConfig.Environment.GetEnvironmentInstances(env)
		if len(envInstances) == 0 {
			logrus.Warnf("Environment '%s' not found in configuration, skipping scheduled send", env)
			continue
		}

		if err := s.sendSampleForEnvironmentWithMetrics(env, metrics); err != nil {
			logrus.Errorf("Failed to send scheduled sample for environment '%s': %v", env, err)
		} else {
			logrus.Debugf("Successfully sent scheduled sample for environment: %s", env)
		}
	}
}

// sendSampleForEnvironment sends a sample to a specific environment
func (s *SamplerService) sendSampleForEnvironment(environment string) error {
	return s.sendSampleForEnvironmentWithMetrics(environment, s.config.Metrics)
}

// sendSampleForEnvironmentWithMetrics sends the given metrics to a specific environment
func (s *SamplerService) sendSampleForEnvironmentWithMetrics(environment string, metrics map[string]float64) error {
	// Convert metrics map to metriclist array format expected by receiver
	metricList := make([]map[string]interface{}, 0, len(metrics))
	for name, value := range metrics {
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
