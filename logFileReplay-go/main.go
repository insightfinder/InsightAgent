package main

import (
	"flag"
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"insightagent-go/collectors/logfilereplay"
	. "insightagent-go/insightfinder"
	"path/filepath"
	"sync"
	"time"
)

func main() {
	defer func() {
		if r := recover(); r != nil {
			log.Error().Msgf("InsightAgent failed. %v", r)
		}
	}()

	debug := flag.Bool("debug", false, "sets log level to debug")
	collector := flag.String("collector", "", "sets collector type")
	flag.Parse()

	zerolog.SetGlobalLevel(zerolog.InfoLevel)

	if *debug {
		IsDebugMode = true
		zerolog.SetGlobalLevel(zerolog.DebugLevel)
	}
	if *collector != "" {
		DefaultCollectorType = *collector
	}

	log.Info().Msg("Starting InsightAgent...")

	// Read configuration files
	configFileList := GetConfigFiles("conf.d")
	configFiles := make([]string, 0)

	for _, configFilePath := range configFileList {
		_, err := configparser.NewConfigParserFromFile(configFilePath)
		if err != nil {
			_ = fmt.Errorf("failed to read config file: %s\n%s", configFilePath, err.Error())
			return
		}
		configFiles = append(configFiles, configFilePath)
	}
	log.Info().Msgf("Loaded %d configuration files from conf.d/", len(configFiles))

	// Process based each config file
	var wg sync.WaitGroup

	for _, configFilePath := range configFiles {
		wg.Add(1)
		go workerMain(configFilePath, &wg)
	}

	wg.Wait()
	log.Info().Msg("InsightAgent all workers completed")
}

func startCollecting(ifConfig *IFConfig,
	configFile *configparser.ConfigParser,
	samplingTime time.Time,
) {
	// Start collecting data
	switch ifConfig.CollectorType {
	case "logfilereplay":
		logfilereplay.Collect(ifConfig, configFile, samplingTime)
	default:
		panic(fmt.Sprintf("Unsupported collector type: %s", ifConfig.CollectorType))
	}
}

func workerMain(configFilePath string, wg *sync.WaitGroup) {
	// Get the file name without extension as the worker name
	fileName := filepath.Base(configFilePath)
	configName := fileName[:len(fileName)-len(".ini")]

	defer func() {
		if r := recover(); r != nil {
			log.Error().Msgf("Worker(%s) failed. %v", configName, r)
		}
	}()
	defer wg.Done()

	log.Info().Msgf("Worker(%s) starting...", configName)

	configFile, err := configparser.NewConfigParserFromFile(configFilePath)
	if err != nil {
		log.Error().Msgf("Worker(%s) failed to read config file: %s\n%s",
			configName, configFilePath, err.Error())
		return
	}

	ifConfig := GetIFConfig(configFile)
	ifConfigLog := *ifConfig
	ifConfigLog.LicenseKey = "********"
	ifConfigLog.Token = "********"
	log.Info().Msgf("Worker(%s) IF config: %+v", configName, ifConfigLog)

	CheckProject(ifConfig)

	timeNow := time.Now()
	startCollecting(ifConfig, configFile, timeNow)

	log.Info().Msgf("Worker (%s) finished...", configName)
}
