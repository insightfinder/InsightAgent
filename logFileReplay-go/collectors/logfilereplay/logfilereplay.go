package logfilereplay

import (
	"bufio"
	"bytes"
	"encoding/json"
	"github.com/bigkevmcd/go-configparser"
	"github.com/golang-module/carbon/v2"
	"github.com/rs/zerolog/log"
	"github.com/tidwall/gjson"
	. "insightagent-go/insightfinder"
	"io"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"
)

var STRIP_PORT, _ = regexp.Compile("(.+):\\d+")

const MaxQueueSize = 64

type Chunk struct {
	FileName string
	Offset   int64
	Content  string
}

type ChunkMessage struct {
	Chunk       Chunk
	LogDataList *[]LogData
}

func processFile(sem chan bool, fileName string,
	indexFile *os.File, indexLock *sync.RWMutex, chunks chan<- Chunk, wg *sync.WaitGroup,
	ifConfig *IFConfig, config *Config) {

	defer wg.Done()
	defer func() { <-sem }()

	file, err := os.Open(fileName)
	if err != nil {
		log.Error().Msgf("Error opening file: %s", fileName)
		return
	}
	defer file.Close()

	var lastPos int64 = 0
	var chunkSize = ifConfig.ChunkSizeKb * 1024

	var index map[string]int64
	indexLock.Lock()
	indexFile.Seek(0, io.SeekStart)
	raw, err := io.ReadAll(indexFile)
	if err != nil {
		log.Error().Msgf("Error reading index file: %s", config.IndexFile)
		return
	}
	err = json.Unmarshal(raw, &index)
	if err == nil {
		lastPos, _ = index[fileName]
	}
	indexLock.Unlock()

	_, err = file.Seek(lastPos, io.SeekStart)
	if err != nil {
		log.Error().Msgf("Error seeking file: %s at offset %d bytes", fileName, lastPos)
		return
	}

	log.Info().Msgf("Start processig file %s, last position is %d", fileName, lastPos)
	reader := bufio.NewReader(file)

	var line []byte
	var buffer bytes.Buffer
	var chunk Chunk

	for {
		line, _, err = reader.ReadLine()
		if err != nil && err != io.EOF {
			log.Error().Msgf("Error reading file: %s", fileName)
			return
		}

		if len(line) != 0 {
			buffer.Write(line)
			buffer.WriteByte('\n')
		}

		if buffer.Len() >= chunkSize || err == io.EOF {
			chunk.FileName = fileName
			chunk.Offset = lastPos
			chunk.Content = buffer.String()

			if buffer.Len() == 0 {
				break
			}

			log.Debug().Msgf("Read %d bytes at %s:%d, send to processing", buffer.Len(), fileName, lastPos)
			chunks <- chunk

			lastPos += int64(buffer.Len())
			buffer.Reset()
		}

		if err == io.EOF {
			break
		}
	}

	close(chunks)
}

func processChunks(chunks <-chan Chunk, wg *sync.WaitGroup, processed chan<- ChunkMessage,
	ifConfig *IFConfig, config *Config) {
	defer wg.Done()

	for chunk := range chunks {
		LogDataList := make([]LogData, 0)

		lines := strings.Split(chunk.Content, "\n")
		for _, line := range lines {
			if len(line) == 0 {
				continue
			}

			// Get the component, instance and timestamp from the json data
			component := ""
			instance := config.defaultInstance
			timestamp := int64(0)
			data := line

			if config.componentField != "" {
				component = gjson.Get(line, config.componentField).String()
			}

			if config.instanceField != "" {
				instance = gjson.Get(line, config.instanceField).String()
			}

			if config.timestampField != "" {
				timestampStr := gjson.Get(line, config.timestampField).String()
				if timestampStr != "" {
					cts := carbon.Parse(timestampStr)
					if cts.Error == nil {
						timestamp = cts.TimestampMilli()
						if config.TimezoneOffsetSeconds != 0 {
							timestamp = timestamp + int64(config.TimezoneOffsetSeconds*1000)
						}
					}
				}
			}

			if timestamp == 0 || instance == "" {
				log.Info().Msgf("Cannot get timestamp and instance from log line, ignored")
				log.Debug().Msgf(line)
				continue
			}

			if config.logDataField != "" {
				data = gjson.Get(line, config.logDataField).String()
			}

			LogDataList = append(LogDataList, LogData{
				ComponentName: component,
				Tag:           instance,
				TimeStamp:     timestamp,
				Data:          data,
			})
		}

		processed <- ChunkMessage{
			Chunk:       chunk,
			LogDataList: &LogDataList,
		}
	}

	close(processed)
}

func sendData(ifConfig *IFConfig, message ChunkMessage) {
	chunk := message.Chunk

	defer func() {
		if r := recover(); r != nil {
			log.Error().Msgf("Failed to send log data to IF from %s:%d, ignored", chunk.FileName, chunk.Offset)
		}
	}()

	log.Debug().Msgf("Sending log data to IF from %s:%d", chunk.FileName, chunk.Offset)

	SendLogData(ifConfig, message.LogDataList)

	log.Info().Msgf("Sent log data to IF from %s:%d", chunk.FileName, chunk.Offset)
}

func sendProcessed(processed <-chan ChunkMessage, wg *sync.WaitGroup,
	ifConfig *IFConfig, config *Config,
	indexFile *os.File, indexLock *sync.RWMutex,
	fileName string, startTime time.Time, fileSize int64) {
	defer wg.Done()

	for message := range processed {
		sendData(ifConfig, message)

		indexLock.Lock()
		// seek to the end of the file to refresh the file buffer
		indexFile.Seek(0, io.SeekStart)
		raw, err := io.ReadAll(indexFile)
		if err == nil {
			var index map[string]int64
			err = json.Unmarshal(raw, &index)
			if err != nil {
				index = make(map[string]int64)
			}

			chunk := message.Chunk
			index[chunk.FileName] = chunk.Offset + int64(len(chunk.Content))
			raw, err = json.MarshalIndent(index, "", "  ")
			if err == nil {
				indexFile.Truncate(0)
				indexFile.WriteAt(raw, 0)
			}
		}
		indexLock.Unlock()
	}

	timeSpentSeconds := time.Since(startTime).Seconds()
	timeSpent := float64(timeSpentSeconds) / 60
	rate := float64(fileSize) / (1024 * 1024 * timeSpentSeconds)

	log.Info().Msgf(
		"Finished processing file: %s: %d bytes, time spent %.2f minutes, rate %.2f M/s",
		fileName, fileSize, timeSpent, rate)
}

func Collect(ifConfig *IFConfig,
	configFile *configparser.ConfigParser,
	samplingTime time.Time) {
	defer func() {
		if r := recover(); r != nil {
			log.Error().Msgf("Failed to collect log replay data %v", r)
		}
	}()

	config := getLogReplayConfig(configFile)
	configLog := *config

	log.Info().Msg("Starting LogFileReplay collector")
	log.Info().Msgf("LogFileReplay config: %+v", configLog)

	var wg sync.WaitGroup
	sem := make(chan bool, config.WorkerCount)

	indexFile, err := os.OpenFile(config.IndexFile, os.O_RDWR|os.O_CREATE, 0666)
	if err != nil {
		log.Error().Msgf("Error opening index file: %s", config.IndexFile)
		return
	}
	defer indexFile.Close()

	var indexLock sync.RWMutex

	var totalSize int64 = 0
	var totalFiles = 0
	var allStartTime = time.Now()

	for _, fileName := range config.logFiles {
		sem <- true

		fileInfo, err := os.Stat(fileName)
		if err != nil {
			log.Error().Msgf("Error reading file: %s", fileName)
			continue
		}

		fileSize := fileInfo.Size()
		totalSize += fileSize
		totalFiles += 1

		chunks := make(chan Chunk, MaxQueueSize)
		processed := make(chan ChunkMessage, MaxQueueSize)

		startTime := time.Now()

		wg.Add(1)
		go processFile(sem, fileName, indexFile, &indexLock, chunks, &wg, ifConfig, config)

		wg.Add(1)
		go processChunks(chunks, &wg, processed, ifConfig, config)

		wg.Add(1)
		go sendProcessed(processed, &wg, ifConfig, config, indexFile, &indexLock, fileName, startTime, fileSize)
	}

	wg.Wait()
	timeSpentSeconds := time.Since(allStartTime).Seconds()
	timeSpent := float64(timeSpentSeconds) / 60
	rate := float64(totalSize) / (1024 * 1024 * timeSpentSeconds)

	log.Info().Msgf(
		"Total size of all %d log files: %d bytes, time spent %.2f minutes, rate %.2f M/s",
		totalFiles, totalSize, timeSpent, rate)
	log.Info().Msg("LogFileReplay collector completed")
}
