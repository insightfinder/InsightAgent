package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"

	config "github.com/insightfinder/tarana-agent/configs"
	"github.com/insightfinder/tarana-agent/insightfinder"
	"github.com/insightfinder/tarana-agent/tarana"
	"github.com/insightfinder/tarana-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	fmt.Println("Starting Tarana Agent...")

	// Load configuration
	cfg, err := config.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("Tarana Agent starting...")
	logrus.Infof("Tarana Base URL: %s", cfg.Tarana.BaseURL)
	logrus.Infof("Region IDs: %v", cfg.Tarana.RegionIDs)
	logrus.Infof("Sampling interval: %d seconds", cfg.InsightFinder.SamplingInterval)

	// Initialize services
	taranaService := tarana.NewService(cfg.Tarana)
	ifService := insightfinder.NewService(cfg.InsightFinder)

	// Test Tarana connection
	if err := taranaService.HealthCheck(); err != nil {
		log.Fatalf("Failed to connect to Tarana API: %v", err)
	}
	logrus.Info("Successfully connected to Tarana API")

	// Create worker
	w := worker.NewWorker(cfg, taranaService, ifService)

	// === ENABLE TEST MODE FOR DEVELOPMENT ===
	// Comment out this line when ready for production
	// w.EnableTestMode()

	// Graceful shutdown
	var wg sync.WaitGroup
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	wg.Add(1)
	go func() {
		defer wg.Done()
		w.Start(quit)
	}()

	logrus.Info("Tarana Agent started successfully")

	// Wait for shutdown
	<-quit
	logrus.Info("Shutting down Tarana Agent...")
	wg.Wait()
	logrus.Info("Tarana Agent stopped")
}

func setupLogging(level string) {
	logrus.SetFormatter(&logrus.TextFormatter{
		FullTimestamp:   true,
		TimestampFormat: "2006-01-02 15:04:05",
	})

	switch level {
	case "DEBUG":
		logrus.SetLevel(logrus.DebugLevel)
	case "INFO":
		logrus.SetLevel(logrus.InfoLevel)
	case "WARN":
		logrus.SetLevel(logrus.WarnLevel)
	case "ERROR":
		logrus.SetLevel(logrus.ErrorLevel)
	default:
		logrus.SetLevel(logrus.InfoLevel)
	}
}
