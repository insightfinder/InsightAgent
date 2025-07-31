package logfilereplay

import (
	"bufio"
	"bytes"
	"encoding/json"
	"github.com/bigkevmcd/go-configparser"
	"github.com/golang-module/carbon/v2"
	"github.com/rs/zerolog/log"
	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
	. "insightagent-go/insightfinder"
	"io"
	"math"
	"os"
	"regexp"
	"strconv"
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

func processFile(sem chan bool, fileName string, lastPos int64,
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

	var chunkSize = ifConfig.ChunkSizeKb * 1024

	_, err = file.Seek(lastPos, io.SeekStart)
	if err != nil {
		log.Error().Msgf("Error seeking file: %s at offset %d bytes", fileName, lastPos)
		return
	}

	log.Info().Msgf("Start processing file %s, last position is %d", fileName, lastPos)

	// Use a buffered reader for the JSON decoder
	reader := bufio.NewReader(file)
	decoder := json.NewDecoder(reader)

	var buffer bytes.Buffer
	var chunk Chunk
	var lines []string

	for {
		// Read one complete JSON object
		var jsonObj map[string]interface{}
		err = decoder.Decode(&jsonObj)

		if err != nil {
			if err == io.EOF {
				break
			}
			log.Error().Msgf("Error decoding JSON from file %s: %v", fileName, err)
			// Try to skip to next valid JSON by reading until newline
			reader.ReadLine()
			continue
		}

		// Convert back to JSON string
		jsonBytes, err := json.Marshal(jsonObj)
		if err != nil {
			log.Error().Msgf("Error marshaling JSON object: %v", err)
			continue
		}

		lineStr := string(jsonBytes)
		buffer.Write(jsonBytes)
		buffer.WriteByte('\n')
		lines = append(lines, lineStr)

		// Check if we should send the chunk
		shouldSendChunk := buffer.Len() >= chunkSize

		if shouldSendChunk {
			// Create JSON array from lines
			jsonArray, jsonErr := json.Marshal(lines)
			if jsonErr != nil {
				log.Error().Msgf("Error marshaling lines to JSON array: %v", jsonErr)
				chunk.Content = buffer.String()
			} else {
				chunk.Content = string(jsonArray)
			}

			chunk.FileName = fileName
			chunk.Offset = lastPos

			log.Debug().Msgf("Read %d bytes (%d lines) at %s:%d, wrapped in JSON array, send to processing",
				buffer.Len(), len(lines), fileName, lastPos)
			chunks <- chunk

			lastPos += int64(buffer.Len())
			buffer.Reset()
			lines = lines[:0]
		}
	}

	// Send remaining data if any
	if buffer.Len() > 0 {
		jsonArray, jsonErr := json.Marshal(lines)
		if jsonErr != nil {
			log.Error().Msgf("Error marshaling remaining lines to JSON array: %v", jsonErr)
			chunk.Content = buffer.String()
		} else {
			chunk.Content = string(jsonArray)
		}

		chunk.FileName = fileName
		chunk.Offset = lastPos

		log.Debug().Msgf("Read final %d bytes (%d lines) at %s:%d, wrapped in JSON array, send to processing",
			buffer.Len(), len(lines), fileName, lastPos)
		chunks <- chunk
	}

	close(chunks)
}

func processChunks(chunks <-chan Chunk, wg *sync.WaitGroup, processed chan<- ChunkMessage,
	ifConfig *IFConfig, config *Config) {
	defer wg.Done()
	jsonLinesProcessed := 0

	for chunk := range chunks {
		LogDataList := make([]LogData, 0)

		// Parse the JSON array from chunk content
		var lines []string
		err := json.Unmarshal([]byte(chunk.Content), &lines)
		if err != nil {
			log.Error().Msgf("Error unmarshaling JSON array from chunk %s:%d: %v",
				chunk.FileName, chunk.Offset, err)
			// Fallback to original string splitting if JSON parsing fails
			lines = strings.Split(chunk.Content, "\n")
		}

		for _, line := range lines {
			if len(line) == 0 {
				continue
			}

			jsonLinesProcessed++

			// Get the component, instance and timestamp from the json data
			component := ""
			instance := ""
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
					var err error
					var timestampNum int64
					// Try to parse the timestamp as a number first
					if strings.Contains(timestampStr, ".") {
						timestampNumFloat, _ := strconv.ParseFloat(timestampStr, 64)
						timestampNum = int64(timestampNumFloat)
					} else {
						timestampNum, err = strconv.ParseInt(timestampStr, 10, 64)
					}

					if err == nil {

						// If the digits are not 13. Adjust the timestamp
						if len(timestampStr) != 13 {
							lengthDiff := 13 - len(timestampStr)
							if lengthDiff > 0 {
								// If the digits are less than 13, add 0s to the end
								timestampNum = timestampNum * int64(math.Pow10(lengthDiff))
							} else {
								// If the digits are more than 13, remove the extra digits
								timestampNum = timestampNum / int64(math.Pow10(-lengthDiff))
							}
						}
						timestamp = timestampNum
					} else {
						// Try to parse the timestamp as a date string
						cts := carbon.Parse(timestampStr)
						if cts.Error == nil {
							timestamp = cts.TimestampMilli()
							if config.TimezoneOffsetSeconds != 0 {
								timestamp = timestamp + int64(config.TimezoneOffsetSeconds*1000)
							}
						}
					}
				}
			}

			if timestamp == 0 {
				log.Error().Msgf("Timestamp field %s is missing in the log", config.timestampField)
				log.Debug().Msgf(line)
				continue
			}

			if instance == "" {
				// Try default instance
				if config.defaultInstance != "" {
					instance = config.defaultInstance
					log.Warn().Msgf("Instance field %s is missing in the log, default to %s", config.timestampField, instance)
					log.Debug().Msgf(line)
				} else {
					log.Error().Msgf("Instance field %s is missing in the log", config.instanceField)
					log.Debug().Msgf(line)
					continue
				}
			}

			// Make safe instanceName
			instance = makeSafeInstanceName(instance)

			if config.logRawDataField != "" {
				// Use the raw data field as the root of the document
				filteredData := gjson.Get(line, config.logRawDataField)
				if filteredData.IsObject() {
					LogDataList = append(LogDataList, LogData{
						ComponentName: component,
						Tag:           instance,
						TimeStamp:     timestamp,
						Data:          filteredData.Value().(map[string]any),
					})
				} else {
					LogDataList = append(LogDataList, LogData{
						ComponentName: component,
						Tag:           instance,
						TimeStamp:     timestamp,
						Data:          filteredData.Value().(string),
					})
				}
			} else {
				// Only Save selected fields
				if config.logDataField != "" {
					filteredData := `{}`
					var err error
					dataFields := strings.Split(config.logDataField, ",")
					for _, field := range dataFields {
						value := gjson.Get(data, field)
						filteredData, err = sjson.SetRaw(filteredData, field, value.Raw)
						if err != nil {
							log.Error().Msgf("Error filtering data field: %s", field)
						}
					}
					LogDataList = append(LogDataList, LogData{
						ComponentName: component,
						Tag:           instance,
						TimeStamp:     timestamp,
						Data:          filteredData,
					})
				}
			}
		}

		processed <- ChunkMessage{
			Chunk:       chunk,
			LogDataList: &LogDataList,
		}
	}
	log.Info().Msgf("Sent %d JSON lines from the file.",
		jsonLinesProcessed)

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
	fileName string, startTime time.Time, dataSize int64) {
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
	rate := float64(dataSize) / (1024 * 1024 * timeSpentSeconds)

	log.Info().Msgf(
		"Finished processing file: %s: %d bytes, time spent %.2f minutes, rate %.2f M/s",
		fileName, dataSize, timeSpent, rate)
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

	var indexMap map[string]int64
	indexLock.Lock()
	indexFile.Seek(0, io.SeekStart)
	raw, err := io.ReadAll(indexFile)
	if err != nil {
		log.Error().Msgf("Error reading index file: %s", config.IndexFile)
		return
	}
	err = json.Unmarshal(raw, &indexMap)
	if err != nil {
		indexMap = make(map[string]int64)
	}
	indexLock.Unlock()

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
		lastPos := int64(0)
		lastPos, _ = indexMap[fileName]
		dataSize := fileSize - lastPos
		totalSize += dataSize
		totalFiles += 1

		chunks := make(chan Chunk, MaxQueueSize)
		processed := make(chan ChunkMessage, MaxQueueSize)

		startTime := time.Now()

		wg.Add(1)
		go processFile(sem, fileName, lastPos, indexFile, &indexLock, chunks, &wg, ifConfig, config)

		wg.Add(1)
		go processChunks(chunks, &wg, processed, ifConfig, config)

		wg.Add(1)
		go sendProcessed(processed, &wg, ifConfig, config, indexFile, &indexLock, fileName, startTime, dataSize)
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

func makeSafeInstanceName(rawInstanceName string) string {
	return strings.Replace(rawInstanceName, "_", "-", -1)
}
