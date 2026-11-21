package main

import (
	"flag"
	"os"
	"strings"
	"sync"
	"time"

	config "github.com/insightfinder/servicenow-monitor/configs"
	"github.com/insightfinder/servicenow-monitor/insightfinder"
	"github.com/insightfinder/servicenow-monitor/servicenow"
	"github.com/sirupsen/logrus"
)

// Runs one health-check pass over every enabled ServiceNow instance and sends
// Success/Failure metrics to InsightFinder, then exits. Schedule it with cron
// (e.g. every 30 minutes) to match insightfinder.sampling_interval.
func main() {
	configPath := flag.String("config", "configs/config.yaml", "path to config file")
	flag.Parse()

	logrus.SetFormatter(&logrus.TextFormatter{FullTimestamp: true, TimestampFormat: "2006-01-02 15:04:05"})

	cfg, err := config.LoadConfig(*configPath)
	if err != nil {
		logrus.Fatalf("Failed to load configuration: %v", err)
	}
	setupLogging(cfg.Agent.LogLevel)

	ifService := insightfinder.NewService(cfg.InsightFinder)
	if err := ifService.CreateProjectIfNotExist(); err != nil {
		logrus.Fatalf("InsightFinder project setup failed: %v", err)
	}

	now := time.Now().UnixMilli()
	var (
		mu      sync.Mutex
		wg      sync.WaitGroup
		metrics []insightfinder.MetricData
		failed  int
	)

	for _, inst := range cfg.ServiceNow.Instances {
		if !inst.Enabled {
			logrus.Infof("[%s] Disabled, skipping", inst.Name)
			continue
		}
		wg.Add(1)
		go func(inst config.ServiceNowInstance) {
			defer wg.Done()

			start := time.Now()
			success, failure := 1.0, 0.0
			if err := servicenow.NewClient(inst, cfg.ServiceNow).HealthCheck(); err != nil {
				logrus.Errorf("[%s] Health check FAILED: %v", inst.Name, err)
				success, failure = 0, 1
			} else {
				logrus.Infof("[%s] Health check OK (%s)", inst.Name, time.Since(start).Round(time.Millisecond))
			}

			mu.Lock()
			defer mu.Unlock()
			if failure == 1 {
				failed++
			}
			metrics = append(metrics, insightfinder.MetricData{
				InstanceName:  inst.Name,
				ComponentName: cfg.InsightFinder.ComponentName,
				Timestamp:     now,
				Data: map[string]float64{
					"Success": success,
					"Failure": failure,
				},
			})
		}(inst)
	}
	wg.Wait()

	if err := ifService.SendMetrics(metrics); err != nil {
		logrus.Fatalf("Failed to send metrics to InsightFinder: %v", err)
	}
	logrus.Infof("Run complete: %d instance(s) checked, %d failed", len(metrics), failed)
	os.Exit(0)
}

func setupLogging(level string) {
	switch strings.ToUpper(level) {
	case "DEBUG":
		logrus.SetLevel(logrus.DebugLevel)
	case "WARN":
		logrus.SetLevel(logrus.WarnLevel)
	case "ERROR":
		logrus.SetLevel(logrus.ErrorLevel)
	default:
		logrus.SetLevel(logrus.InfoLevel)
	}
}
