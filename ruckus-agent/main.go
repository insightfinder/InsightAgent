package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"

	config "github.com/insightfinder/ruckus-agent/configs"
	"github.com/insightfinder/ruckus-agent/insightfinder"
	"github.com/insightfinder/ruckus-agent/ruckus"
	"github.com/insightfinder/ruckus-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	fmt.Println("Starting Ruckus Agent...")

	// Load configuration
	cfg, err := config.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("Ruckus Agent starting...")
	logrus.Infof("Controller: %s:%d", cfg.Ruckus.ControllerHost, cfg.Ruckus.ControllerPort)
	logrus.Infof("Sampling interval: %d seconds", cfg.InsightFinder.SamplingInterval)

	// Initialize services
	ruckusService := ruckus.NewService(cfg.Ruckus)
	ifService := insightfinder.NewService(cfg.InsightFinder)

	// Test Ruckus connection
	if err := ruckusService.Authenticate(); err != nil {
		log.Fatalf("Failed to authenticate with Ruckus controller: %v", err)
	}
	logrus.Info("Successfully authenticated with Ruckus controller")

	// Create worker
	w := worker.NewWorker(cfg, ruckusService, ifService)

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

	logrus.Info("Ruckus Agent started successfully")

	// Wait for shutdown
	<-quit
	logrus.Info("Shutting down Ruckus Agent...")
	wg.Wait()
	logrus.Info("Ruckus Agent stopped")
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
