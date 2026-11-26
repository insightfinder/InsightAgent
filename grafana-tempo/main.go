package main

import (
	"context"
	"errors"
	"flag"
	"os"
	"os/signal"
	"syscall"

	config "github.com/insightfinder/grafana-tempo-agent/configs"
	"github.com/insightfinder/grafana-tempo-agent/insightfinder"
	"github.com/insightfinder/grafana-tempo-agent/tempo"
	"github.com/insightfinder/grafana-tempo-agent/worker"
	"github.com/sirupsen/logrus"
)

func main() {
	configPath := flag.String("c", "configs/config.yaml", "config file path")
	flag.Parse()

	logrus.SetFormatter(&logrus.TextFormatter{FullTimestamp: true})
	logrus.Info("Starting Grafana Tempo Agent...")

	cfg, err := config.LoadConfig(*configPath)
	if err != nil {
		logrus.Fatalf("Failed to load configuration: %v", err)
	}
	setupLogging(cfg.Agent.LogLevel)

	logrus.Infof("Tempo endpoint: %s", cfg.Tempo.Endpoint)
	logrus.Infof("TraceQL query: %s", cfg.Tempo.Query)

	tempoService := tempo.NewService(cfg.Tempo)

	var ifService *insightfinder.Service
	if cfg.InsightFinder.DryRun {
		logrus.Info("Dry run: traces are fetched from Tempo and logged, nothing is sent to InsightFinder")
	} else {
		ifService, err = insightfinder.NewService(cfg.InsightFinder)
		if err != nil {
			logrus.Fatalf("Failed to create InsightFinder service: %v", err)
		}
		defer ifService.Close()
		logrus.Infof("Trace server: %s, project: %s", cfg.InsightFinder.TraceServer, cfg.InsightFinder.ProjectName)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	w := worker.NewWorker(cfg, tempoService, ifService)
	if err := w.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
		logrus.Errorf("Grafana Tempo Agent stopped with error: %v", err)
		os.Exit(1)
	}
	logrus.Info("Grafana Tempo Agent stopped")
}

func setupLogging(level string) {
	parsed, err := logrus.ParseLevel(level)
	if err != nil {
		parsed = logrus.InfoLevel
	}
	logrus.SetLevel(parsed)
}
