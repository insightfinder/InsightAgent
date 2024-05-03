package main

import (
	"context"
	"fmt"
	"if-jaeger-agent/insightfinder"
	"if-jaeger-agent/jaeger_client"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"
)

func createJaegerClientFromConfig(filename string) *jaeger_client.JaegerClient {
	client := jaeger_client.NewJaegerClient("http://localhost:16686")
	return &client
}

/**
 * Get all the config files under the directory conf.d
 */
func getConfigFiles() []string {

	currentFolder, err := os.Getwd()
	if err != nil {
		slog.Error("Error getting current directory")
	}
	configFolder := currentFolder + "/conf.d"
	configFiles, err := filepath.Glob(configFolder + "/*.yaml")
	if err != nil {
		slog.Error("Error scanning config files")
		panic(err)
	}

	if len(configFiles) == 0 {
		slog.Error("No config file found in" + configFolder)
		panic("Program exited 1")
	}

	return configFiles
}

func main() {
	//configFiles := getConfigFiles()
	//var jaegerJobList []*jaeger_client.JaegerClient
	//
	//for _, configFile := range configFiles {
	//	slog.Info("Processing config file: " + configFile)
	//	jaegerJob := createJaegerClientFromConfig(configFile)
	//	jaegerJobList = append(jaegerJobList, jaegerJob)
	//}

	ifapp := insightfinder.NewInsightFinder("https://stg.insightfinder.com",
		"maoyuwang",
		"",
		"maoyu-test-trace-agent-1",
		"maoyu-test-trace-agent")

	result := ifapp.CreateProjectIfNotExist()
	fmt.Print(result)
	jaegerClient := jaeger_client.JaegerClient{
		Endpoint:  "http://18.212.200.99:16686",
		StartTime: time.Now().Add(-5 * time.Minute),
		EndTime:   time.Now(),
		Service:   "appserver",
		Limit:     1500,
		Step:      time.Duration(1) * time.Minute,
	}
	spansChn := make(chan *jaeger_client.Span, 100)
	var traceWg sync.WaitGroup

	traceWg.Add(1)
	go func() {
		defer traceWg.Done()
		jaegerClient.GetTraces(context.Background(), spansChn)
	}()

	for {
		select {
		case span := <-spansChn:
			fmt.Print(span)
		}
	}

	traceWg.Wait()
}
