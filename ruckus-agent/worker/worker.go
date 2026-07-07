package worker

import (
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"
	"unicode"

	config "github.com/insightfinder/ruckus-agent/configs"
	"github.com/insightfinder/ruckus-agent/insightfinder"
	"github.com/insightfinder/ruckus-agent/pkg/models"
	"github.com/insightfinder/ruckus-agent/ruckus"
	"github.com/sirupsen/logrus"
)

// normalizeMACIdentifier mirrors the netexperience/zabbix agents' MAC
// normalization: replace ':' with '-', trim leading/trailing '-', trim
// whitespace, and require at least one alphanumeric character. No case
// conversion — the original casing must be preserved so the same physical
// device produces the same instance identifier across agents.
func normalizeMACIdentifier(mac string) string {
	mac = strings.TrimSpace(mac)
	if mac == "" {
		return ""
	}
	converted := strings.TrimSpace(strings.Trim(strings.ReplaceAll(mac, ":", "-"), "-"))
	if converted == "" || !containsAlnum(converted) {
		return ""
	}
	return converted
}

// normalizeSerialIdentifier mirrors the netexperience/zabbix agents' serial
// normalization: trim whitespace and require at least one alphanumeric
// character.
func normalizeSerialIdentifier(serial string) string {
	serial = strings.TrimSpace(serial)
	if serial == "" || !containsAlnum(serial) {
		return ""
	}
	return serial
}

func containsAlnum(s string) bool {
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return true
		}
	}
	return false
}

type Worker struct {
	config               *config.Config
	ruckusService        *ruckus.Service
	insightFinderService *insightfinder.Service
	testMode             bool
	// Add streaming configuration
	chunkSize     int
	maxBufferSize int
	// Stats tracking
	statsLock    sync.RWMutex
	currentStats *CollectionStats
	// Device inventory lookup (MAC/serial -> venue/component/serial)
	deviceLookup   ruckus.DeviceLookup
	deviceLookupMu sync.RWMutex
}

func (w *Worker) getDeviceLookup() ruckus.DeviceLookup {
	w.deviceLookupMu.RLock()
	defer w.deviceLookupMu.RUnlock()
	return w.deviceLookup
}

func (w *Worker) setDeviceLookup(dl ruckus.DeviceLookup) {
	w.deviceLookupMu.Lock()
	w.deviceLookup = dl
	w.deviceLookupMu.Unlock()
}

// refreshDeviceLookup fetches all AP identifiers and refreshes the inventory lookup
func (w *Worker) refreshDeviceLookup() {
	identifiers, err := w.ruckusService.GetAllAPIdentifiers()
	if err != nil {
		logrus.Errorf("DeviceLookup: failed to fetch AP identifiers, keeping existing lookup: %v", err)
		return
	}
	w.setDeviceLookup(w.ruckusService.RefreshDeviceLookup(identifiers, w.getDeviceLookup()))
}

type CollectionStats struct {
	TotalAPs       int
	ProcessedAPs   int
	OnlineAPs      int
	FlaggedAPs     int
	TotalClients   int
	HighAirtime24G int
	HighAirtime5G  int
	ErrorCount     int
	StartTime      time.Time
	LastUpdateTime time.Time
}

func NewWorker(config *config.Config, ruckusService *ruckus.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:               config,
		ruckusService:        ruckusService,
		insightFinderService: ifService,
		testMode:             false,
		chunkSize:            1000, // Default chunk size for bulk processing
		maxBufferSize:        1000, // Default buffer size for metrics
		currentStats:         &CollectionStats{},
	}
}

// Configure streaming parameters
func (w *Worker) SetStreamingConfig(chunkSize, maxBufferSize int) {
	w.chunkSize = chunkSize
	w.maxBufferSize = maxBufferSize
	logrus.Infof("Streaming configured: chunk size=%d, buffer size=%d", chunkSize, maxBufferSize)
}

func (w *Worker) Start(quit <-chan os.Signal) {
	// Initialize and validate InsightFinder connection
	logrus.Info("Initializing InsightFinder connection...")

	// Create project if it doesn't exist
	if !w.insightFinderService.CreateProjectIfNotExist() {
		logrus.Fatal("Failed to create/verify InsightFinder project")
		return
	}

	logrus.Info("InsightFinder connection established successfully")

	// Load device lookup from disk; if empty (first run), refresh synchronously so
	// the first metric cycle has correct instance/component/zone data.
	w.setDeviceLookup(ruckus.LoadDeviceLookup())
	if len(w.getDeviceLookup()) == 0 {
		logrus.Info("DeviceLookup cache empty, running initial refresh before first metric cycle...")
		w.refreshDeviceLookup()
	} else if ruckus.DeviceLookupIsStale() {
		go w.refreshDeviceLookup()
	}

	// Use sampling_interval from InsightFinder config instead of collection_interval
	samplingInterval := time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second
	ticker := time.NewTicker(samplingInterval)
	defer ticker.Stop()

	deviceLookupTicker := time.NewTicker(24 * time.Hour)
	defer deviceLookupTicker.Stop()

	logrus.Infof("Starting data collection with %d second intervals", w.config.InsightFinder.SamplingInterval)

	// Run initial collection
	w.collectAndSendStreaming()

	for {
		select {
		case <-ticker.C:
			w.collectAndSendStreaming()
		case <-deviceLookupTicker.C:
			go w.refreshDeviceLookup()
		case <-quit:
			logrus.Info("Worker received shutdown signal")
			return
		}
	}
}

// applyDeviceMetadata sets instance name, display name, component name, zone and IP
// on a metric using the device inventory lookup. It returns false when the metric
// must be discarded (not reported to InsightFinder).
//
// A device is discarded if it is not found in the inventory (looked up by
// MAC -> Serial -> IP -> Name during RefreshDeviceLookup), or if the inventory
// record has no usable instance identifier.
//
// Value mapping (fallbacks in parentheses):
//   - Instance:     MAC {inv_mac} > SERIAL {inv_serial} > JIRAKEY {object_key} (else discard)
//   - Display name: inventory name (config.DefaultComponentName, e.g. AP-Ruckus)
//   - Component:    inventory manufacturer-device_class, excluding NONE-NONE (config.DefaultComponentName)
//   - Zone:         inventory venue (UNKNOWN)
//   - IP:           inventory ip_address (Ruckus AP IP)
func (w *Worker) applyDeviceMetadata(metric *models.MetricData, ap *models.APDetail) bool {
	devInfo, found := w.getDeviceLookup().Lookup(ap.APMAC)
	if !found {
		return false
	}

	invMAC := normalizeMACIdentifier(devInfo.MACAddress)
	invSerial := normalizeSerialIdentifier(devInfo.SerialNumber)

	switch {
	case invMAC != "":
		metric.InstanceName = "MAC " + invMAC
	case invSerial != "":
		metric.InstanceName = "SERIAL " + invSerial
	case devInfo.ObjectKey != "":
		metric.InstanceName = "JIRAKEY " + devInfo.ObjectKey
	default:
		return false
	}

	fallback := w.config.Ruckus.DefaultComponentName

	metric.DisplayName = devInfo.Name
	if metric.DisplayName == "" {
		metric.DisplayName = fallback
	}

	metric.ComponentName = fallback
	if devInfo.ComponentName != "" && devInfo.ComponentName != "NONE-NONE" {
		metric.ComponentName = devInfo.ComponentName
	}

	metric.Zone = "UNKNOWN"
	if devInfo.Venue != "" {
		metric.Zone = devInfo.Venue
	}

	metric.IP = ap.IP
	if devInfo.IPAddress != "" {
		metric.IP = devInfo.IPAddress
	}

	return true
}

// New streaming collection method using bulk query
func (w *Worker) collectAndSendStreaming() {
	logrus.Info("Starting streaming data collection cycle with bulk query")
	startTime := time.Now()

	// Initialize stats
	w.statsLock.Lock()
	w.currentStats = &CollectionStats{
		StartTime:      startTime,
		LastUpdateTime: startTime,
	}
	w.statsLock.Unlock()

	// Health check before collection
	if err := w.ruckusService.HealthCheck(); err != nil {
		logrus.Errorf("Health check failed: %v", err)
		return
	}

	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// First, fetch all client data for RSSI/SNR enrichment
	logrus.Info("Fetching client data for RSSI/SNR enrichment...")
	clientMap, clientErr := w.ruckusService.GetAllClientsWithRSSISNR(ctx)
	if clientErr != nil {
		logrus.Errorf("Failed to fetch client data: %v", clientErr)
		logrus.Info("Continuing without client enrichment data...")
		clientMap = make(map[string][]models.ClientInfo)
	} else {
		logrus.Infof("Successfully fetched client data for %d APs", len(clientMap))
	}

	// Process metrics buffer
	var metricsBuffer []models.MetricData
	var bufferMutex sync.Mutex

	// Test mode file handles
	var rawDataFile *os.File
	var err error

	if w.testMode {
		rawDataFile, err = w.createTestFile("bulk_ap_data")
		if err != nil {
			logrus.Errorf("Failed to create test file: %v", err)
			return
		}
		defer rawDataFile.Close()

		// Start JSON array
		rawDataFile.WriteString("[\n")
	}

	var firstChunk bool = true
	totalProcessed := 0

	// Processor function for each chunk
	processor := func(apChunk []models.APDetail) error {
		// Enrich AP data with client metrics (RSSI/SNR) with threshold configuration
		enrichedChunk := ruckus.EnrichAPDataWithClientMetrics(apChunk, clientMap,
			w.config.Threshold.MinClientsRSSIThreshold,
			w.config.Threshold.MinClientsSNRThreshold)

		// Update stats
		w.updateStats(enrichedChunk)

		// Convert to metrics
		var chunkMetrics []models.MetricData
		for _, ap := range enrichedChunk {
			metric := ap.ToMetricData(w.ruckusService.Config.SendComponentNameAsAP, &w.config.MetricFilter)
			chunkMetrics = append(chunkMetrics, *metric)
		}

		// Process zone mappings
		chunkMetrics = models.ProcessZoneMappings(chunkMetrics)

		// Apply device inventory metadata (instance name, display name, component, zone, ip).
		// Devices not found in the inventory are discarded and not reported to InsightFinder.
		filtered := make([]models.MetricData, 0, len(chunkMetrics))
		for i := range chunkMetrics {
			if w.applyDeviceMetadata(&chunkMetrics[i], &enrichedChunk[i]) {
				filtered = append(filtered, chunkMetrics[i])
			}
		}
		dropped := len(chunkMetrics) - len(filtered)
		if dropped > 0 {
			logrus.Infof("Discarded %d AP(s) not found in device inventory", dropped)
		}
		chunkMetrics = filtered

		if w.testMode {
			// Write chunk to test file
			if err := w.writeChunkToTestFile(rawDataFile, enrichedChunk, &firstChunk); err != nil {
				return fmt.Errorf("failed to write test data: %v", err)
			}
		} else {
			// Add to buffer for production sending
			bufferMutex.Lock()
			metricsBuffer = append(metricsBuffer, chunkMetrics...)

			// Send buffer if it's getting full
			if len(metricsBuffer) >= w.maxBufferSize {
				if err := w.sendBufferedMetrics(metricsBuffer); err != nil {
					logrus.Errorf("Failed to send buffered metrics: %v", err)
					bufferMutex.Unlock()
					return err
				}
				metricsBuffer = metricsBuffer[:0] // Clear buffer
			}
			bufferMutex.Unlock()
		}

		totalProcessed += len(apChunk)
		logrus.Infof("Processed %d APs (total: %d)", len(apChunk), totalProcessed)

		return nil
	}

	// Use the new bulk streaming method instead of individual AP queries
	err = w.ruckusService.GetAllAPDetailsStreamingBulk(ctx, processor, w.chunkSize)
	if err != nil {
		logrus.Errorf("Bulk streaming collection failed: %v", err)
		return
	}

	// Send remaining buffered metrics in production mode
	if !w.testMode {
		bufferMutex.Lock()
		if len(metricsBuffer) > 0 {
			if err := w.sendBufferedMetrics(metricsBuffer); err != nil {
				logrus.Errorf("Failed to send final buffered metrics: %v", err)
			}
		}
		bufferMutex.Unlock()
	}

	// Finalize test mode files
	if w.testMode {
		rawDataFile.WriteString("\n]")
		if err := w.saveStreamingStats(); err != nil {
			logrus.Errorf("Failed to save streaming stats: %v", err)
		}
	}

	duration := time.Since(startTime)
	w.statsLock.RLock()
	finalStats := *w.currentStats
	w.statsLock.RUnlock()

	logrus.Infof("Bulk streaming collection completed: %d APs processed in %v (%.2f APs/sec)",
		finalStats.ProcessedAPs, duration, float64(finalStats.ProcessedAPs)/duration.Seconds())
}
