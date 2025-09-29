package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"

	config "github.com/insightfinder/edgecore-agent/configs"
	"github.com/insightfinder/edgecore-agent/edgecore"
	"github.com/insightfinder/edgecore-agent/insightfinder"
	"github.com/insightfinder/edgecore-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	fmt.Println("Starting EdgeCore Agent...")

	// Load configuration
	cfg, err := config.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("EdgeCore Agent starting...")
	logrus.Infof("EdgeCore Base URL: %s", cfg.EdgeCore.BaseURL)
	logrus.Infof("Service Provider ID: %s", cfg.EdgeCore.ServiceProviderID)
	logrus.Infof("Sampling interval: %d seconds", cfg.InsightFinder.SamplingInterval)

	// Initialize services
	edgecoreService := edgecore.NewService(cfg.EdgeCore)
	ifService := insightfinder.NewService(cfg.InsightFinder)

	// Test EdgeCore connection
	if err := edgecoreService.HealthCheck(); err != nil {
		log.Fatalf("Failed to connect to EdgeCore API: %v", err)
	}
	logrus.Info("Successfully connected to EdgeCore API")

	// Create worker
	w := worker.NewWorker(cfg, edgecoreService, ifService)

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

	logrus.Info("EdgeCore Agent started successfully")

	// Wait for shutdown
	<-quit
	logrus.Info("Shutting down EdgeCore Agent...")
	wg.Wait()
	logrus.Info("EdgeCore Agent stopped")
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
