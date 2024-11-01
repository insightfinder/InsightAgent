package main

import (
	ConfigService "grafana-agent/service/config"
	DbService "grafana-agent/service/db"
	GrafanaService "grafana-agent/service/grafana"
	WorkerFactory "grafana-agent/worker"
	"log/slog"
	"sync"
	"time"
)

func main() {
	var config = ConfigService.LoadConfig()
	if config == nil {
		slog.Error("Failed to load config file")
		return
	} else {
		slog.Info("Config loaded successfully")
	}

	// Setup Grafana Service
	grafanaQueryDelay, err := time.ParseDuration(config.Grafana.QueryDelay)
	if err != nil {
		slog.Error("Failed to parse Grafana Query Delay")
		return
	}

	grafanaService := GrafanaService.CreateGrafanaService(config.Grafana.URL, config.Grafana.Token, config.Grafana.Username, config.Grafana.Password, config.Grafana.DataSourceUID, grafanaQueryDelay)

	dbService := DbService.CreateDbService()

	// Get the run interval
	runInterval, err := time.ParseDuration(config.InsightFinder.RunInterval)
	if err != nil {
		slog.Error("Failed to parse runInterval")
		return
	}

	// Run workers
	var wg sync.WaitGroup
	for _, projectConfig := range config.Projects {
		wg.Add(1)
		go func(projectConfig ConfigService.ProjectConfig) {
			defer wg.Done()
			worker := WorkerFactory.CreateWorker(&projectConfig,
				&config.InsightFinder,
				&config.Query,
				grafanaService,
				dbService)
			worker.Run(time.Now().Add(-runInterval), time.Now())
		}(projectConfig)
	}

	wg.Wait()
	slog.Info("All workers have finished")
}
