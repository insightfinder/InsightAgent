package logfilereplay

import (
	"github.com/bigkevmcd/go-configparser"
	"github.com/bmatcuk/doublestar/v4"
	"github.com/rs/zerolog/log"
	. "insightagent-go/insightfinder"
	"os"
	"sort"
	"strings"
	"time"
)

const SectionName = "logfilereplay"

type Config struct {
	logFiles              []string
	componentField        string
	instanceField         string
	logDataField          string
	logRawDataField       string
	defaultInstance       string
	defaultComponent      string
	timestampField        string
	TimezoneOffsetSeconds int
	TrunkSize             int
	WorkerCount           int
	IndexFile             string
}

func getLogReplayConfig(p *configparser.ConfigParser) *Config {
	var logFilesStr = GetConfigString(p, SectionName, "log_files", true)
	var defaultInstance = GetConfigString(p, SectionName, "default_instance", false)
	var defaultComponent = GetConfigString(p, SectionName, "default_component", false)
	var componentField = GetConfigString(p, SectionName, "component_field", false)
	var instanceField = GetConfigString(p, SectionName, "instance_field", false)
	var timestampField = GetConfigString(p, SectionName, "timestamp_field", true)
	var workerCount = GetConfigInt(p, SectionName, "worker_count", false, 1)
	var logDataField = GetConfigString(p, SectionName, "log_data_field", false)
	var logRawDataField = GetConfigString(p, SectionName, "log_raw_data_field", false)

	if defaultInstance == "" && instanceField == "" {
		panic("Either default_instance or instance_field must be set")
	}

	workDir, err := os.Getwd()
	if err != nil {
		panic("Error getting working directory")
	}

	var logFilePaths = strings.Split(logFilesStr, ";")
	var logFiles []string
	fsys := os.DirFS(workDir)
	for _, logFilePath := range logFilePaths {
		files, err := doublestar.Glob(fsys, logFilePath)
		if err != nil {
			log.Warn().Msgf("Error reading log file: %s, %s", logFilePath, err)
		} else {
			logFiles = append(logFiles, files...)
		}
	}
	// Sort files by name
	sort.Strings(logFiles)

	log.Info().Msgf("Found %d log files", len(logFiles))

	var timestampTimezone = GetConfigString(p, SectionName, "timestamp_timezone", false)
	if timestampTimezone == "" {
		timestampTimezone = "UTC"
	}
	location, _ := time.LoadLocation(timestampTimezone)
	_, timezoneOffset := time.Now().In(location).Zone()

	config := Config{
		logFiles:              logFiles,
		componentField:        componentField,
		logDataField:          logDataField,
		logRawDataField:       logRawDataField,
		defaultInstance:       defaultInstance,
		defaultComponent:      defaultComponent,
		instanceField:         instanceField,
		timestampField:        timestampField,
		TimezoneOffsetSeconds: timezoneOffset,
		TrunkSize:             1024 * 64,
		WorkerCount:           workerCount,
		IndexFile:             "logfilereplay_index.json",
	}

	return &config
}
