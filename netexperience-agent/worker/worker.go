package worker

import (
	"fmt"
	"os"
	"sync"
	"time"

	config "github.com/insightfinder/netexperience-agent/configs"
	"github.com/insightfinder/netexperience-agent/insightfinder"
	"github.com/insightfinder/netexperience-agent/netexperience"
	"github.com/insightfinder/netexperience-agent/pkg/models"
	"github.com/sirupsen/logrus"
)

// Worker handles the main data collection and processing logic
type Worker struct {
	config        *config.Config
	netexpService *netexperience.Service
	ifService     *insightfinder.Service
	stopChan      chan struct{}
	wg            sync.WaitGroup
}

// NewWorker creates a new worker instance
func NewWorker(cfg *config.Config, netexpService *netexperience.Service, ifService *insightfinder.Service) *Worker {
	return &Worker{
		config:        cfg,
		netexpService: netexpService,
		ifService:     ifService,
		stopChan:      make(chan struct{}),
	}
}

// Start starts the worker
func (w *Worker) Start(quit <-chan os.Signal) {
	logrus.Info("Worker starting...")

	// Initialize and validate InsightFinder connection
	logrus.Info("Initializing InsightFinder connection...")

	// Create project if it doesn't exist
	if !w.ifService.CreateProjectIfNotExist() {
		logrus.Fatal("Failed to create/verify InsightFinder project")
		return
	}

	logrus.Info("InsightFinder connection established successfully")

	// Start token refresh routine
	w.wg.Add(1)
	go func() {
		defer w.wg.Done()
		w.netexpService.StartTokenRefreshRoutine(w.stopChan)
	}()

	// Initial cache refresh
	if err := w.refreshCaches(); err != nil {
		logrus.Errorf("Initial cache refresh failed: %v", err)
	}

	// Start main collection loop
	ticker := time.NewTicker(time.Duration(w.config.InsightFinder.SamplingInterval) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			w.collectAndSendMetrics()
		case <-quit:
			logrus.Info("Shutdown signal received, stopping worker...")
			close(w.stopChan)
			return
		}
	}
}

// refreshCaches refreshes customer and equipment caches if needed
func (w *Worker) refreshCaches() error {
	var errors []error

	// Refresh customer cache if needed
	if w.netexpService.ShouldRefreshCustomerCache() {
		logrus.Info("Refreshing customer cache...")
		if err := w.netexpService.RefreshCustomerCache(); err != nil {
			errors = append(errors, fmt.Errorf("customer cache refresh failed: %w", err))
		}
	}

	// Refresh equipment cache if needed
	if w.netexpService.ShouldRefreshEquipmentCache() {
		logrus.Info("Refreshing equipment cache...")
		if err := w.netexpService.RefreshEquipmentCache(); err != nil {
			errors = append(errors, fmt.Errorf("equipment cache refresh failed: %w", err))
		}
	}

	// Refresh equipment IP cache if needed
	if w.netexpService.ShouldRefreshEquipmentIPCache() {
		logrus.Info("Refreshing equipment IP cache...")
		if err := w.netexpService.RefreshEquipmentIPCache(); err != nil {
			errors = append(errors, fmt.Errorf("equipment IP cache refresh failed: %w", err))
		}
	}

	if len(errors) > 0 {
		return fmt.Errorf("cache refresh errors: %v", errors)
	}

	return nil
}

// collectAndSendMetrics collects metrics and sends them to InsightFinder
func (w *Worker) collectAndSendMetrics() {
	logrus.Info("Starting metric collection cycle...")
	cycleStartTime := time.Now()

	// Refresh caches if needed
	if err := w.refreshCaches(); err != nil {
		logrus.Warnf("Cache refresh warning: %v", err)
	}

	// Calculate time range for metrics (last 1 minute)
	now := time.Now()
	toTime := now.Add(-1 * time.Minute).Truncate(time.Minute).UnixMilli()
	fromTime := now.Add(-2 * time.Minute).Truncate(time.Minute).UnixMilli()

	logrus.Debugf("Collecting metrics for time range: %d to %d", fromTime, toTime)

	// Get all customers
	customers := w.netexpService.GetCachedCustomers()
	if len(customers) == 0 {
		logrus.Warn("No customers found in cache")
		return
	}

	logrus.Infof("Processing metrics for %d customers...", len(customers))
	processingStartTime := time.Now()

	// Process each customer
	allMetrics := make([]*models.EquipmentMetrics, 0)
	processedCustomers := 0
	totalEquipmentProcessed := 0

	for _, customer := range customers {
		customerMetrics := w.processCustomer(customer, fromTime, toTime)
		allMetrics = append(allMetrics, customerMetrics...)
		processedCustomers++
		totalEquipmentProcessed += len(customerMetrics)

		// Log progress every 10 customers
		if processedCustomers%10 == 0 {
			percentage := float64(processedCustomers) / float64(len(customers)) * 100
			elapsed := time.Since(processingStartTime)
			rate := float64(processedCustomers) / elapsed.Seconds()
			remainingCustomers := len(customers) - processedCustomers
			eta := time.Duration(float64(remainingCustomers)/rate) * time.Second

			logrus.Infof("Progress: %d/%d customers (%.1f%%) | Equipment metrics: %d | Rate: %.1f customers/s | ETA: %v",
				processedCustomers, len(customers), percentage, totalEquipmentProcessed, rate, eta.Round(time.Second))
		}
	}

	processingDuration := time.Since(processingStartTime)

	if len(allMetrics) == 0 {
		logrus.Warn("No metrics collected in this cycle")
		return
	}

	logrus.Infof("Processed %d customers with %d equipment metrics in %v, sending to InsightFinder...",
		processedCustomers, len(allMetrics), processingDuration.Round(time.Millisecond))

	// Send metrics to InsightFinder
	sendStartTime := time.Now()
	if err := w.sendMetricsToIF(allMetrics); err != nil {
		logrus.Errorf("Failed to send metrics to InsightFinder: %v", err)
	} else {
		sendDuration := time.Since(sendStartTime)
		cycleDuration := time.Since(cycleStartTime)
		logrus.Infof("Successfully sent metrics to InsightFinder in %v (total cycle: %v)",
			sendDuration.Round(time.Millisecond), cycleDuration.Round(time.Millisecond))
	}
}
