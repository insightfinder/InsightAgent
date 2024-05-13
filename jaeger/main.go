package main

import (
	"fmt"
	"if-jaeger-agent/insightfinder"
	"if-jaeger-agent/jaeger_client"
	"log/slog"
	"sync"
	"time"
)

func main() {
	//configFiles := getConfigFiles()
	//var jaegerJobList []*jaeger_client.JaegerClient
	//
	//for _, configFile := range configFiles {
	//	slog.Info("Processing config file: " + configFile)
	//	jaegerJob := createJaegerClientFromConfig(configFile)
	//	jaegerJobList = append(jaegerJobList, jaegerJob)
	//}
	configFiles := getConfigFiles()
	for _, configFile := range configFiles {
		slog.Info("Processing config file: " + configFile)

		// Create a new InsightFinder client from the YAML config file
		// ifApp := insightfinder.NewInsightFinderFromYAML(configFile)
		// fmt.Println(ifapp.CloudType)
		jaegerApp := jaeger_client.CreateJaegerClientFromConfig(configFile)
		fmt.Println(jaegerApp.Service)
	}

	ifapp := insightfinder.NewInsightFinder("https://stg.insightfinder.com",
		"maoyuwang",
		"",
		"maoyu-test-trace-agent-2024-0509-3",
		"Trace",
		"maoyu-test-trace-agent-2024-0509-3",
	)

	ifapp.CreateProjectIfNotExist()
	jaegerClient := jaeger_client.JaegerClient{
		Endpoint:  "http://:16686",
		StartTime: time.Now().Add(-5 * time.Minute),
		EndTime:   time.Now(),
		Service:   "appserver",
		Limit:     1000,
		Step:      time.Duration(1) * time.Minute,
	}

	spanChan := make(chan *jaeger_client.Span, 1000000) // Create a channel to hold spans
	wg := sync.WaitGroup{}

	// Start the Spans stream
	wg.Add(1)
	go func() {
		defer wg.Done()
		jaegerClient.StreamTraces(spanChan)
		close(spanChan)
	}()

	// Start workers
	numWorkers := 10
	for i := 0; i < numWorkers; i++ {
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
						ifapp.SendLogData(time.UnixMicro(span.StartTime).UnixMilli(), jaeger_client.GetTagValue("http.hostname", &span.Tags), "appserver", &span)
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
