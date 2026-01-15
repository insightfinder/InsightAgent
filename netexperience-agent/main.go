package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"sync"
	"syscall"

	config "github.com/insightfinder/netexperience-agent/configs"
	"github.com/insightfinder/netexperience-agent/insightfinder"
	"github.com/insightfinder/netexperience-agent/netexperience"
	"github.com/insightfinder/netexperience-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	fmt.Println("Starting NetExperience Agent...")

	// Load configuration
	cfg, err := config.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Setup logging
	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("NetExperience Agent starting...")
	logrus.Infof("NetExperience API URL: %s", cfg.NetExperience.BaseURL)
	logrus.Infof("Sampling interval: %d seconds", cfg.InsightFinder.SamplingInterval)

	// Initialize services
	netexpService := netexperience.NewService(cfg.NetExperience)
	ifService := insightfinder.NewService(cfg.InsightFinder)

	// Initialize NetExperience service (login)
	if err := netexpService.Initialize(); err != nil {
		log.Fatalf("Failed to initialize NetExperience service: %v", err)
	}
	logrus.Info("Successfully initialized NetExperience service")

	// Create worker
	w := worker.NewWorker(cfg, netexpService, ifService)

	// Graceful shutdown
	var wg sync.WaitGroup
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	wg.Add(1)
	go func() {
		defer wg.Done()
		w.Start(quit)
	}()

	logrus.Info("NetExperience Agent started successfully")

	// Wait for shutdown
	<-quit
	logrus.Info("Shutting down NetExperience Agent...")
	wg.Wait()
	logrus.Info("NetExperience Agent stopped")
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
