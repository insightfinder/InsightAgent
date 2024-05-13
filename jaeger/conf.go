package main

import (
	"log/slog"
	"os"
	"path/filepath"
)

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
