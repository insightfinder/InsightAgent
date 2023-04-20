package main

import (
	"fmt"
	"log"
	"path/filepath"

	"github.com/bigkevmcd/go-configparser"
)

func absFilePath(filename string) string {
	if filename == "" {
		filename = ""
	}
	absFilePath, err := filepath.Abs(filename)
	if err != nil {
		log.Fatal(err)
	}
	return absFilePath
}

func parseConfig(configPath string) {
	log.Output(2, "parsing the file"+configPath)
	p, err := configparser.NewConfigParserFromFile(configPath)
	if err != nil {
		log.Fatal(err)
	}
	v, err := p.Get("prometheus", "prometheus_uri")
	if err != nil {
		println(err)
	}
	fmt.Println(v)
}

func getConfigFiles(configRelativePath string) []string {
	if configRelativePath == "" {
		// default value for configuration path
		configRelativePath = "conf.d"
	}
	configPath := absFilePath(configRelativePath)
	log.Output(2, "Reading config files from"+configPath)
	allConfigs, err := filepath.Glob(configPath + "/*.ini")
	if err != nil {
		log.Fatal(err)
	}
	if len(allConfigs) == 0 {
		log.Fatal("No config file found in", configPath)
	}
	return allConfigs
}

func main() {
	allConfigs := getConfigFiles("")
	for i := 0; i < len(allConfigs); i++ {
		parseConfig(allConfigs[i])
	}

}
