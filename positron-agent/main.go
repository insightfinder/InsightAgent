package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"

	config "github.com/insightfinder/positron-agent/configs"
	"github.com/insightfinder/positron-agent/insightfinder"
	"github.com/insightfinder/positron-agent/positron"
	"github.com/insightfinder/positron-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	fmt.Println("Starting Positron Agent...")

	// Load configuration
	cfg, err := config.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("Positron Agent starting...")
	logrus.Infof("Controller: %s:%d", cfg.Positron.ControllerHost, cfg.Positron.ControllerPort)
	logrus.Infof("Sampling interval: %d seconds", cfg.InsightFinder.SamplingInterval)

	// Initialize services
	positronService := positron.NewService(cfg.Positron)
	ifService := insightfinder.NewService(cfg.InsightFinder)

	// Test Positron connection
	if err := positronService.HealthCheck(); err != nil {
		log.Fatalf("Failed to connect to Positron controller: %v", err)
	}
	logrus.Info("Successfully connected to Positron controller")

	// Create worker
	w := worker.NewWorker(cfg, positronService, ifService)

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

	logrus.Info("Positron Agent started successfully")

	// Wait for shutdown
	<-quit
	logrus.Info("Shutting down Positron Agent...")
	wg.Wait()
	logrus.Info("Positron Agent stopped")
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
