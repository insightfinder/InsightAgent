package main

import (
	"flag"
	"fmt"
	"math"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/sirupsen/logrus"
	"github.com/tarana/gnmic-agent/collector"
	"github.com/tarana/gnmic-agent/config"
	"github.com/tarana/gnmic-agent/insightfinder"
	"github.com/tarana/gnmic-agent/models"
)

var (
	configPath = flag.String("config", "config/config.yaml", "Path to configuration file")
	logger     *logrus.Logger
)

func init() {
	logger = logrus.New()
	logger.SetFormatter(&logrus.TextFormatter{
		FullTimestamp:   true,
		TimestampFormat: "2006-01-02 15:04:05",
	})
}

func main() {
	flag.Parse()

	logger.Info("========================================================")
	logger.Info("Tarana gNMIc Agent Starting...")
	logger.Info("========================================================")

	// Load configuration
	cfg, err := config.LoadConfig(*configPath)
	if err != nil {
		logger.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg)

	logger.Infof("Configuration loaded successfully")
	logger.Infof("Agent Name: %s", cfg.Agent.Name)
	logger.Infof("Log Level: %s", cfg.Agent.LogLevel)
	logger.Infof("InfluxDB URL: %s", cfg.InfluxDB.URL)
	logger.Infof("InsightFinder Enabled: %v", cfg.InsightFinder.Enabled)

	// Create metrics collector
	collectorCfg := collector.CollectorConfig{
		InfluxURL:    cfg.InfluxDB.URL,
		InfluxToken:  cfg.InfluxDB.Token,
		InfluxOrg:    cfg.InfluxDB.Org,
		InfluxBucket: cfg.InfluxDB.Bucket,
		TimeRange:    cfg.Collector.TimeRange,
	}
	metricsCollector := collector.NewCollector(&collectorCfg, logger) // Create InsightFinder service if enabled
	var ifService *insightfinder.Service
	if cfg.InsightFinder.Enabled {
		ifService = insightfinder.NewService(cfg.InsightFinder)
		logger.Info("InsightFinder service initialized")
	} else {
		logger.Warn("InsightFinder is disabled in configuration")
	}

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Create ticker for periodic collection
	ticker := time.NewTicker(time.Duration(cfg.InsightFinder.SamplingInterval) * time.Second)
	defer ticker.Stop()

	logger.Infof("Starting metrics collection loop (interval: %d seconds)", cfg.InsightFinder.SamplingInterval)

	// Run first collection immediately
	collectAndSend(metricsCollector, ifService, cfg.InsightFinder.Enabled)

	// Main loop
	for {
		select {
		case <-ticker.C:
			collectAndSend(metricsCollector, ifService, cfg.InsightFinder.Enabled)
		case sig := <-sigChan:
			logger.Infof("Received signal: %v", sig)
			logger.Info("Shutting down gracefully...")
			return
		}
	}
}

// collectAndSend collects metrics and sends them to InsightFinder
func collectAndSend(collector *collector.Collector, ifService *insightfinder.Service, enabled bool) {
	logger.Info("========================================================")
	logger.Info("Starting metrics collection...")
	logger.Info("========================================================")

	// Collect RN devices
	logger.Info("Collecting RN device metrics...")
	rnDevices, err := collector.CollectRNDevices()
	if err != nil {
		logger.Errorf("Failed to collect RN devices: %v", err)
	} else {
		logger.Infof("Collected %d RN devices", len(rnDevices))
	}

	// Collect BN devices
	logger.Info("Collecting BN device metrics...")
	bnDevices, err := collector.CollectBNDevices()
	if err != nil {
		logger.Errorf("Failed to collect BN devices: %v", err)
	} else {
		logger.Infof("Collected %d BN devices", len(bnDevices))
	}

	// Send to InsightFinder if enabled
	if enabled && ifService != nil {
		logger.Info("Converting metrics for InsightFinder...")

		var allMetrics []models.MetricData

		// Convert RN devices to InsightFinder format
		for _, device := range rnDevices {
			if device.Hostname == "" {
				continue // Skip devices without hostnames
			}

			metricData := models.MetricData{
				Timestamp:     device.Timestamp.UnixMilli(),
				InstanceName:  insightfinder.CleanDeviceName(device.Hostname),
				ComponentName: "RN-Tarana",
				IP:            getIPFromSource(device.Source),
				Data:          make(map[string]interface{}),
			}

			// Add all metrics (convert to float64/int as appropriate)
			// Add all metrics - check for empty strings, convert to float, and apply absolute value
			if device.DLSNR != "" {
				if val := parseFloat(device.DLSNR); val != 0 || device.DLSNR == "0" {
					metricData.Data["DL SNR"] = math.Abs(val)
				}
			}
			if device.ULSNR != "" {
				if val := parseFloat(device.ULSNR); val != 0 || device.ULSNR == "0" {
					metricData.Data["UL SNR"] = math.Abs(val)
				}
			}
			if device.PathLoss != "" {
				if val := parseFloat(device.PathLoss); val != 0 || device.PathLoss == "0" {
					metricData.Data["Path Loss"] = math.Abs(val)
				}
			}
			if device.RFRange != "" {
				if val := parseFloat(device.RFRange); val != 0 || device.RFRange == "0" {
					metricData.Data["RF Range"] = math.Abs(val)
				}
			}
			if device.RXSignal0 != "" {
				if val := parseFloat(device.RXSignal0); val != 0 || device.RXSignal0 == "0" {
					metricData.Data["RX Signal 0"] = math.Abs(val)
				}
			}
			if device.RXSignal1 != "" {
				if val := parseFloat(device.RXSignal1); val != 0 || device.RXSignal1 == "0" {
					metricData.Data["RX Signal 1"] = math.Abs(val)
				}
			}
			if device.RXSignal2 != "" {
				if val := parseFloat(device.RXSignal2); val != 0 || device.RXSignal2 == "0" {
					metricData.Data["RX Signal 2"] = math.Abs(val)
				}
			}
			if device.RXSignal3 != "" {
				if val := parseFloat(device.RXSignal3); val != 0 || device.RXSignal3 == "0" {
					metricData.Data["RX Signal 3"] = math.Abs(val)
				}
			}

			allMetrics = append(allMetrics, metricData)
		}

		// Convert BN devices to InsightFinder format
		for _, device := range bnDevices {
			if device.Hostname == "" {
				continue // Skip devices without hostnames
			}

			metricData := models.MetricData{
				Timestamp:     device.Timestamp.UnixMilli(),
				InstanceName:  insightfinder.CleanDeviceName(device.Hostname),
				ComponentName: "BN-Tarana",
				IP:            getIPFromSource(device.Source),
				Data:          make(map[string]interface{}),
			}

			// Add all metrics - convert negative values to positive
			if device.ActiveConnections != "" {
				if val := parseInt(device.ActiveConnections); val != 0 || device.ActiveConnections == "0" {
					metricData.Data["Active Connections"] = val
				}
			}
			if device.RXSignal0 != "" {
				if val := parseFloat(device.RXSignal0); val != 0 || device.RXSignal0 == "0" {
					metricData.Data["RX Signal 0"] = math.Abs(val)
				}
			}
			if device.RXSignal1 != "" {
				if val := parseFloat(device.RXSignal1); val != 0 || device.RXSignal1 == "0" {
					metricData.Data["RX Signal 1"] = math.Abs(val)
				}
			}
			if device.RXSignal2 != "" {
				if val := parseFloat(device.RXSignal2); val != 0 || device.RXSignal2 == "0" {
					metricData.Data["RX Signal 2"] = math.Abs(val)
				}
			}
			if device.RXSignal3 != "" {
				if val := parseFloat(device.RXSignal3); val != 0 || device.RXSignal3 == "0" {
					metricData.Data["RX Signal 3"] = math.Abs(val)
				}
			}

			allMetrics = append(allMetrics, metricData)
		}

		logger.Infof("Prepared %d metric data points for InsightFinder", len(allMetrics))

		// Send to InsightFinder
		if len(allMetrics) > 0 {
			// Ensure project exists before sending metrics
			if !ifService.CreateMetricsProjectIfNotExist() {
				logger.Error("Failed to create or verify InsightFinder project, skipping metric send")
			} else {
				if err := ifService.SendMetrics(allMetrics); err != nil {
					logger.Errorf("Failed to send metrics to InsightFinder: %v", err)
				} else {
					logger.Info("Successfully sent metrics to InsightFinder")
				}
			}
		} else {
			logger.Warn("No metrics to send to InsightFinder")
		}
	}

	logger.Info("Collection cycle completed")
	logger.Info("========================================================")
}

// setupLogging configures the logger based on configuration
func setupLogging(cfg *config.Config) {
	// Set log level
	level, err := logrus.ParseLevel(cfg.Agent.LogLevel)
	if err != nil {
		logger.Warnf("Invalid log level '%s', using 'info'", cfg.Agent.LogLevel)
		level = logrus.InfoLevel
	}
	logger.SetLevel(level)

	// Setup log file if specified
	if cfg.Agent.LogFile != "" {
		// Create logs directory if it doesn't exist
		logDir := filepath.Dir(cfg.Agent.LogFile)
		if err := os.MkdirAll(logDir, 0755); err != nil {
			logger.Errorf("Failed to create log directory: %v", err)
			return
		}

		// Open log file
		logFile, err := os.OpenFile(cfg.Agent.LogFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
		if err != nil {
			logger.Errorf("Failed to open log file: %v", err)
			return
		}

		// Write to both file and stdout
		logger.SetOutput(logFile)
		logger.Infof("Logging to file: %s", cfg.Agent.LogFile)
	}

	logger.Infof("Log level set to: %s", level.String())
}

// getIPFromSource extracts IP address from source (removes port)
func getIPFromSource(source string) string {
	if idx := strings.Index(source, ":"); idx != -1 {
		return source[:idx]
	}
	return source
}

// parseFloat safely converts string to float64
func parseFloat(s string) float64 {
	var f float64
	fmt.Sscanf(s, "%f", &f)
	return f
}

// parseInt safely converts string to int
func parseInt(s string) int {
	var i int
	fmt.Sscanf(s, "%d", &i)
	return i
}
