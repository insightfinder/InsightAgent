package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/insightfinder/splunk-forwarder/configs"
	"github.com/insightfinder/splunk-forwarder/insightfinder"
	"github.com/insightfinder/splunk-forwarder/splunk"
	"github.com/insightfinder/splunk-forwarder/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	cfg, err := configs.LoadConfig("configs/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	setupLogging(cfg.Agent.LogLevel)

	logrus.Info("Starting Splunk Forwarder Agent")
	logrus.Infof("Splunk server:      %s", cfg.Splunk.ServerURL)
	logrus.Infof("IF project:         %s", cfg.InsightFinder.LogsProjectName)
	logrus.Infof("Sampling interval:  %ds", cfg.InsightFinder.SamplingInterval)
	logrus.Infof("Enabled queries:")
	for _, q := range cfg.Splunk.Queries {
		if q.Enabled {
			logrus.Infof("  [%s] %s", q.Name, q.Query)
		}
	}

	splunkSvc := splunk.NewService(cfg.Splunk)
	ifSvc := insightfinder.NewService(cfg.InsightFinder)

	w := worker.New(cfg, splunkSvc, ifSvc)

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	done := make(chan struct{})
	go func() {
		w.Start(quit)
		close(done)
	}()

	logrus.Info("Agent running. Press Ctrl+C to stop.")
	<-done
	logrus.Info("Agent stopped.")
}

func setupLogging(level string) {
	switch level {
	case "DEBUG":
		logrus.SetLevel(logrus.DebugLevel)
	case "WARN":
		logrus.SetLevel(logrus.WarnLevel)
	case "ERROR":
		logrus.SetLevel(logrus.ErrorLevel)
	default:
		logrus.SetLevel(logrus.InfoLevel)
	}
	logrus.SetFormatter(&logrus.TextFormatter{FullTimestamp: true})
}
