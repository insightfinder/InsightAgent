package main

import (
	"flag"
	"fmt"
	"if-jaeger-agent/insightfinder"
	"if-jaeger-agent/jaeger_client"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"
)

func main() {

	var numWorkers = flag.Int("w", 10, "Number of workers")
	var configFileName = flag.String("c", "config.yaml", "Config yaml file")
	flag.Parse()

	// Get the absolute path of the config file
	configFile, err := filepath.Abs(*configFileName)
	if err != nil {
		slog.Error("Error getting absolute path of config file")
		panic(err)
	}

	// Create a new InsightFinder client from the YAML config file
	ifApp := insightfinder.NewInsightFinderFromYAML(configFile)
	checkProjectResult := ifApp.CreateProjectIfNotExist()
	if !checkProjectResult {
		slog.Error("Error creating project on InsightFinder. Exiting...")
		os.Exit(1)
	}
	jaegerApp := jaeger_client.CreateJaegerClientFromConfig(configFile)

	spanChan := make(chan *jaeger_client.Span, 1000000) // Create a channel to hold spans
	wg := sync.WaitGroup{}

	// Start the Spans stream
	wg.Add(1)
	go func() {
		defer wg.Done()
		jaegerApp.StreamTraces(spanChan)
		close(spanChan)
	}()

	// Start workers
	for i := 0; i < *numWorkers; i++ {
		slog.Info(fmt.Sprintf("Starting worker %d", i))
		wg.Add(1)
		go func(workerId int) {
			var count uint = 0
			for {
				select {
				case span, ok := <-spanChan:
					if !ok {
						slog.Warn(fmt.Sprintf("Worker %d finished processing %d spans", workerId, count))
						wg.Done()
						return
					} else {
						count++

						// Extract additional tags from the span
						instanceValue := jaeger_client.GetFirstTagValue(jaegerApp.InstanceTags, &span.Tags)
						componentValue := jaeger_client.GetFirstTagValue(jaegerApp.ComponentTags, &span.Tags)

						ifApp.SendLogData(time.UnixMicro(span.StartTime).UnixMilli(), instanceValue, componentValue, &span)
						if count%100 == 0 {
							slog.Info(fmt.Sprintf("Worker %d processed %d spans", workerId, count))
						}
					}
				}
			}
		}(i)
	}

	wg.Wait() // Wait for all processing to complete
}
