package main

import (
	"log"
	"sync"

	"github.com/bigkevmcd/go-configparser"
	golangif "github.com/insightfinder/InsightAgent/tree/master/golang-IF"
)

func workerProcess(configPath string, wg *sync.WaitGroup) {
	defer wg.Done()
	_ = log.Output(2, "Parsing the config file: "+configPath)
	p, err := configparser.NewConfigParserFromFile(configPath)
	if err != nil {
		panic(err)
	}
	var IFConfig = golangif.GetInsightFinderConfig(p)
	golangif.CheckProject(IFConfig)
	config := readOpensearchConfig(p)
	data := getOpenSearchData(config)
	logData := processOSData(config, data)
	golangif.SendLogData(logData, IFConfig)
}

func main() {
	allConfigs := golangif.GetConfigFiles("")
	wg := new(sync.WaitGroup)
	numOfConfigs := len(allConfigs)
	wg.Add(numOfConfigs)

	for i := 0; i < numOfConfigs; i++ {
		go workerProcess(allConfigs[i], wg)
	}
	wg.Wait()
	log.Output(1, "[LOG] All workers have finsihed. The agent will terminate by itself.")
}
