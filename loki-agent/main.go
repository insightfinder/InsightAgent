package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	config "github.com/insightfinder/loki-agent/configs"
	"github.com/insightfinder/loki-agent/insightfinder"
	"github.com/insightfinder/loki-agent/loki"
	"github.com/insightfinder/loki-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	logrus.Info("Starting Loki Agent...")

	// Load configuration
	cfg, err := config.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("Loki Agent starting...")
	logrus.Infof("Loki Base URL: %s", cfg.Loki.BaseURL)
	logrus.Infof("Number of queries: %d", len(cfg.Loki.Queries))
	logrus.Infof("Sampling interval: %d seconds", cfg.InsightFinder.SamplingInterval)

	// Initialize services
	lokiService := loki.NewService(cfg.Loki)
	ifService := insightfinder.NewService(cfg.InsightFinder, cfg.Loki)

	// Validate InsightFinder configuration (not required for historical download mode)
	if cfg.Agent.Mode != "historical" {
		if !ifService.Validate() {
			log.Fatalf("InsightFinder configuration validation failed")
		}
	}

	// // Test Loki connection
	// if err := lokiService.HealthCheck(); err != nil {
	// 	log.Fatalf("Failed to connect to Loki API: %v", err)
	// }
	// logrus.Info("Successfully connected to Loki API")

	// List enabled queries
	logrus.Info("Enabled queries:")
	for _, query := range cfg.Loki.Queries {
		if query.Enabled {
			logrus.Infof("  - %s: %s", query.Name, query.Query)
		}
	}

	// Create worker
	w := worker.NewWorker(cfg, lokiService, ifService)

	// === ENABLE TEST MODE FOR DEVELOPMENT ===
	// Comment out this line when ready for production
	// w.EnableTestMode()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	done := make(chan struct{})
	go func() {
		w.Start(quit)
		close(done)
	}()

	logrus.Info("Loki Agent started successfully")
	logrus.Info("Press Ctrl+C to stop...")

	// Block until the worker finishes (one-shot modes exit naturally;
	// continuous mode exits when a signal is received).
	<-done
	logrus.Info("Loki Agent stopped")
}

func setupLogging(level string) {
	// Simple logging setup - could be enhanced with structured logging
	switch level {
	case "DEBUG":
		log.SetFlags(log.LstdFlags | log.Lshortfile)
	case "INFO":
		log.SetFlags(log.LstdFlags)
	case "WARN":
		log.SetFlags(log.LstdFlags)
	case "ERROR":
		log.SetFlags(log.LstdFlags)
	default:
		log.SetFlags(log.LstdFlags)
	}
}
