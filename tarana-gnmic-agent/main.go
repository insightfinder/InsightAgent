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
	"github.com/tarana/gnmic-agent/devicelookup"
	"github.com/tarana/gnmic-agent/insightfinder"
	"github.com/tarana/gnmic-agent/models"
)

var (
	configPath   = flag.String("config", "config/config.yaml", "Path to configuration file")
	logger       *logrus.Logger
	deviceLookup devicelookup.Lookup
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

	deviceLookup = devicelookup.Load()

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Create ticker for periodic collection
	ticker := time.NewTicker(time.Duration(cfg.InsightFinder.SamplingInterval) * time.Second)
	defer ticker.Stop()

	logger.Infof("Starting metrics collection loop (interval: %d seconds)", cfg.InsightFinder.SamplingInterval)

	// Run first collection immediately
	collectAndSend(metricsCollector, ifService, cfg.InsightFinder.Enabled, cfg.DeviceInventory, cfg.Defaults)

	// Main loop
	for {
		select {
		case <-ticker.C:
			collectAndSend(metricsCollector, ifService, cfg.InsightFinder.Enabled, cfg.DeviceInventory, cfg.Defaults)
		case sig := <-sigChan:
			logger.Infof("Received signal: %v", sig)
			logger.Info("Shutting down gracefully...")
			return
		}
	}
}

// collectAndSend collects metrics and sends them to InsightFinder
func collectAndSend(collector *collector.Collector, ifService *insightfinder.Service, enabled bool, invCfg config.DeviceInventoryConfig, defaults config.DefaultsConfig) {
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
		refreshDeviceLookupIfNeeded(rnDevices, bnDevices, invCfg)

		logger.Info("Converting metrics for InsightFinder...")

		var allMetrics []models.MetricData

		// Convert RN devices to InsightFinder format
		for _, device := range rnDevices {
			if device.Hostname == "" {
				continue // Skip devices without hostnames
			}

			metricData := buildMetricData(device.Timestamp, device.Hostname, device.MACAddress, device.DeviceID, device.Source, defaults.ComponentNameRN, defaults)

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

			metricData := buildMetricData(device.Timestamp, device.Hostname, device.MACAddress, device.Measurement, device.Source, defaults.ComponentNameBN, defaults)

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

// refreshDeviceLookupIfNeeded refreshes the device inventory cache (MAC -> serial ->
// name, first match wins) from this cycle's devices, if the cache is empty or stale.
func refreshDeviceLookupIfNeeded(rnDevices map[string]*collector.RNDevice, bnDevices map[string]*collector.BNDevice, invCfg config.DeviceInventoryConfig) {
	if len(deviceLookup) > 0 && !devicelookup.IsStale(invCfg.RefreshHours) {
		return
	}

	var items []devicelookup.Identifiers
	for _, d := range rnDevices {
		if d.Hostname == "" {
			continue
		}
		items = append(items, devicelookup.Identifiers{
			MAC:    devicelookup.NormalizeMAC(d.MACAddress),
			Serial: devicelookup.NormalizeSerial(d.DeviceID),
			Name:   insightfinder.CleanDeviceName(d.Hostname),
		})
	}
	for _, d := range bnDevices {
		if d.Hostname == "" {
			continue
		}
		items = append(items, devicelookup.Identifiers{
			MAC:    devicelookup.NormalizeMAC(d.MACAddress),
			Serial: devicelookup.NormalizeSerial(d.Measurement),
			Name:   insightfinder.CleanDeviceName(d.Hostname),
		})
	}
	if len(items) == 0 {
		return
	}

	logger.Infof("Refreshing device inventory lookup for %d devices...", len(items))
	if newLookup := devicelookup.Refresh(invCfg, items); newLookup != nil {
		deviceLookup = newLookup
		logger.Infof("Device inventory lookup refreshed: %d entries", len(deviceLookup))
	}
}

// buildMetricData builds a MetricData for one device, enriching its instance
// name, display name, component name, zone, and IP from the device inventory
// lookup when available (MAC > serial > object key > hostname). A device
// inventory miss never drops the device - it falls back to the device's own
// reported hostname/defaults instead.
func buildMetricData(timestamp time.Time, hostname, mac, serial, source, defaultComponentName string, defaults config.DefaultsConfig) models.MetricData {
	ownMAC := devicelookup.NormalizeMAC(mac)
	ownSerial := devicelookup.NormalizeSerial(serial)
	cleanedName := insightfinder.CleanDeviceName(hostname)

	devInfo := deviceLookup.GetDeviceInfo(ownMAC, ownSerial, cleanedName)
	invMAC := devicelookup.NormalizeMAC(devInfo.MACAddress)
	invSerial := devicelookup.NormalizeSerial(devInfo.SerialNumber)

	// Only inventory-returned identifiers are used here - a device inventory
	// miss falls straight through to the device's own hostname, not its own
	// MAC/serial.
	var instanceName string
	switch {
	case invMAC != "":
		instanceName = "MAC " + invMAC
	case invSerial != "":
		instanceName = "SERIAL " + invSerial
	case devInfo.ObjectKey != "":
		instanceName = "JIRAKEY " + devInfo.ObjectKey
	default:
		instanceName = cleanedName
	}

	// Display name: the device's own raw hostname (as reported, uncleaned) >
	// inventory name. Sent to InsightFinder as-is - it must not collapse to
	// the same formatted "MAC ..."/"SERIAL ..." instanceName. Left blank (not
	// defaulted) when neither source has one, so it's simply omitted.
	displayName := hostname
	if displayName == "" {
		displayName = devInfo.Name
	}

	componentName := defaultComponentName
	if devInfo.ComponentName != "" && devInfo.ComponentName != "NONE-NONE" {
		componentName = devInfo.ComponentName
	}

	// Zone: inventory venue > fallback (an unmatched device must not show a
	// blank zone).
	zone := devInfo.Venue
	if zone == "" {
		zone = defaults.Zone
	}

	// IP: inventory ip_address > the influx "source" tag, but only if that
	// tag is a real address - "0.0.0.0" is gNMI's unset/unreachable-target
	// placeholder, not a real device IP, and must not be reported as one.
	ip := devInfo.IPAddress
	if ip == "" {
		if sourceIP := getIPFromSource(source); sourceIP != "" && sourceIP != "0.0.0.0" {
			ip = sourceIP
		}
	}

	return models.MetricData{
		Timestamp:     timestamp.UnixMilli(),
		InstanceName:  instanceName,
		DisplayName:   displayName,
		ComponentName: componentName,
		Zone:          zone,
		IP:            ip,
		Data:          make(map[string]interface{}),
	}
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
