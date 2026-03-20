package sampler

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/insightfinder/receiver-agent/configs"
	"github.com/sirupsen/logrus"
)

// FaultToleranceService monitors configured metrics per environment and sends a default
// value when no real metric has been received within the configured window.
//
// Tracking key: "<envName>/<metricName>" (e.g. "staging/ServiceNowTicketCreateDelay")
// The window resets whenever a real metric is received OR when a default is successfully sent,
// so defaults fire at most once per window_size interval.
type FaultToleranceService struct {
	config       *configs.Config
	serverURL    string
	mu           sync.Mutex
	lastActivity map[string]time.Time // key: "envName/metricName"
	stopChan     chan struct{}
}

// NewFaultToleranceService creates a new FaultToleranceService.
// serverURL is the receiver endpoint (same URL the sampler uses).
func NewFaultToleranceService(config *configs.Config, serverURL string) *FaultToleranceService {
	return &FaultToleranceService{
		config:       config,
		serverURL:    serverURL,
		lastActivity: make(map[string]time.Time),
		stopChan:     make(chan struct{}),
	}
}

// RecordReceived updates the last-activity timestamp for the given metric in the given
// environment. Call this whenever a real metric value is successfully received.
func (f *FaultToleranceService) RecordReceived(envName, metricName string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	key := envName + "/" + metricName
	f.lastActivity[key] = time.Now()
	logrus.Debugf("Fault tolerance: recorded received for %s", key)
}

// Start begins the monitoring loop. It is a no-op when no metrics have fault tolerance enabled.
func (f *FaultToleranceService) Start() {
	if !f.hasAnyEnabled() {
		logrus.Info("Fault tolerance: no metrics have fault tolerance enabled, not starting")
		return
	}
	logrus.Info("Starting fault tolerance monitoring service")
	f.logEnabledMetrics()
	go f.run()
}

// Stop shuts down the monitoring loop.
func (f *FaultToleranceService) Stop() {
	logrus.Info("Stopping fault tolerance monitoring service...")
	close(f.stopChan)
}

// hasAnyEnabled returns true if at least one metric has fault tolerance enabled.
func (f *FaultToleranceService) hasAnyEnabled() bool {
	for _, envList := range f.config.Environment.Environments {
		for _, env := range envList {
			for _, ft := range env.FaultTolerance {
				if ft.Enabled {
					return true
				}
			}
		}
	}
	return false
}

func (f *FaultToleranceService) logEnabledMetrics() {
	for envName, envList := range f.config.Environment.Environments {
		// Use the first instance's fault_tolerance config as representative for the env.
		if len(envList) == 0 {
			continue
		}
		for metricName, ft := range envList[0].FaultTolerance {
			if ft.Enabled {
				logrus.Infof("Fault tolerance enabled: env=%s metric=%s window=%dm default=%.2f",
					envName, metricName, ft.WindowSize, ft.DefaultValue)
			}
		}
	}
}

func (f *FaultToleranceService) run() {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()

	// Run an initial check immediately on start.
	f.check()

	for {
		select {
		case <-ticker.C:
			f.check()
		case <-f.stopChan:
			logrus.Info("Fault tolerance monitoring service stopped")
			return
		}
	}
}

// check iterates all environments and metrics, and sends defaults for any that have
// exceeded their configured window without a real metric being received.
func (f *FaultToleranceService) check() {
	now := time.Now()

	// Track which (envName, metricName) pairs we have already sent this cycle to avoid
	// duplicate sends when the same environment has multiple instances configured.
	type envMetric struct{ env, metric string }
	sent := map[envMetric]bool{}

	for envName, envList := range f.config.Environment.Environments {
		for _, env := range envList {
			for metricName, ft := range env.FaultTolerance {
				if !ft.Enabled {
					continue
				}

				em := envMetric{envName, metricName}
				if sent[em] {
					continue // Already handled via another instance of the same env.
				}

				key := envName + "/" + metricName
				window := time.Duration(ft.WindowSize) * time.Minute

				f.mu.Lock()
				lastAct, exists := f.lastActivity[key]
				f.mu.Unlock()

				if !exists {
					// First time seeing this key — initialise the window start to now.
					f.mu.Lock()
					f.lastActivity[key] = now
					f.mu.Unlock()
					logrus.Debugf("Fault tolerance: initialised window for %s (window=%dm)", key, ft.WindowSize)
					continue
				}

				elapsed := now.Sub(lastAct)
				if elapsed < window {
					logrus.Debugf("Fault tolerance: %s within window (elapsed=%s, window=%dm)", key, elapsed.Round(time.Second), ft.WindowSize)
					continue
				}

				logrus.Infof("Fault tolerance: metric '%s' in env '%s' not received for %s (window=%dm), sending default value %.2f",
					metricName, envName, elapsed.Round(time.Second), ft.WindowSize, ft.DefaultValue)

				if err := f.sendDefault(envName, metricName, ft.DefaultValue); err != nil {
					logrus.Errorf("Fault tolerance: failed to send default for %s: %v", key, err)
					// Do not update lastActivity on failure — retry next minute.
				} else {
					f.mu.Lock()
					f.lastActivity[key] = now
					f.mu.Unlock()
					sent[em] = true
					logrus.Infof("Fault tolerance: default sent successfully for %s, window reset", key)
				}
			}
		}
	}
}

// sendDefault posts a default metric value for the given environment to the receiver endpoint.
func (f *FaultToleranceService) sendDefault(envName, metricName string, value float64) error {
	payload := map[string]interface{}{
		"agentType":   0, // ServiceNow response type
		"environment": envName,
		"timestamp":   time.Now().UnixMilli(),
		"metriclist": []map[string]interface{}{
			{
				"name":  metricName,
				"value": value,
			},
		},
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal payload: %w", err)
	}

	logrus.Debugf("Fault tolerance: sending default payload for %s/%s: %s", envName, metricName, string(jsonData))

	resp, err := http.Post(f.serverURL, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to send HTTP request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("received non-OK status: %d", resp.StatusCode)
	}

	return nil
}
