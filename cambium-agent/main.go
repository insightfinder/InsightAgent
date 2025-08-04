package main

import (
	"flag"
	"log"

	"cambium-metrics-collector/cambium"
)

func main() {
	// Parse command line arguments
	configPath := flag.String("config", "config/config.yaml", "Path to configuration file")
	flag.Parse()

	// Run the Cambium metrics collector
	if err := cambium.Run(*configPath); err != nil {
		log.Fatalf("Cambium metrics collector failed: %v", err)
	}
}
