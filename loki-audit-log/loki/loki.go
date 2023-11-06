package loki

import (
	"bytes"
	"context"
	"fmt"
	"log"
	"strconv"
	"strings"
	"time"

	"github.com/carlmjohnson/requests"
	"gopkg.in/yaml.v3"
)

type LokiServer struct {
	Endpoint                string
	Username                string
	Password                string
	MaxEntriesLimitPerQuery int
}

const HEALTH_API = "/"
const CONFIG_API = "/config"
const RANGE_QUERY_API = "/loki/api/v1/query_range"
const LOG_QUERY = "{namespace=~\"%s\", pod=\"%s\"}"

func (loki *LokiServer) Query(queryStr string, StartTime string, EndTime string) LogQueryResponseBody {
	var response LogQueryResponseBody
	err := requests.URL(loki.Endpoint+RANGE_QUERY_API).BasicAuth(loki.Username, loki.Password).Param("query", queryStr).Param("start", StartTime).Param("end", EndTime).Param("direction", "forward").Param("limit", strconv.Itoa(loki.MaxEntriesLimitPerQuery)).ToJSON(&response).Fetch(context.Background())
	if err != nil {
		log.Output(2, "Failed to query loki server: "+loki.Endpoint)
		fmt.Println(err.Error())
	}
	return response
}

func (loki *LokiServer) Initialize() {

	// Connectivity check
	var response string
	err := requests.URL(loki.Endpoint+HEALTH_API).BasicAuth(loki.Username, loki.Password).ToString(&response).Fetch(context.Background())
	if err != nil || strings.ReplaceAll(response, "\n", "") != "OK" {
		log.Output(2, "Loki server is not ready: "+response)
		fmt.Print(err)
	} else {
		log.Output(2, "Loki server response: "+response)
	}

	// Setup config
	LokiConfig := loki.getConfig()
	loki.MaxEntriesLimitPerQuery = LokiConfig.LimitsConfig.MaxEntriesLimitPerQuery
}

func (loki *LokiServer) getConfig() LogConfigResponseBody {
	var configResponse bytes.Buffer
	err := requests.URL(loki.Endpoint + CONFIG_API).ToBytesBuffer(&configResponse).Fetch(context.Background())
	if err != nil {
		log.Output(2, "Failed to get config from Loki server.")
	} else {
		log.Output(2, "Read config from Loki server successfully.")
	}

	// Decode response to yaml struct
	config := yaml.NewDecoder(&configResponse)
	var configYaml LogConfigResponseBody
	err = config.Decode(&configYaml)
	if err != nil {
		log.Output(2, "Failed to decode config from Loki server.")
		fmt.Print(configResponse)
	}
	return configYaml
}

func (loki *LokiServer) GetLogData(queryStr string, StartTime time.Time, EndTime time.Time) (resultList []LokiLogData) {
	queryResult := loki.Query(queryStr, StartTime.Format(time.RFC3339), EndTime.Format(time.RFC3339))
	for _, result := range queryResult.Data.Result {
		for _, logData := range result.Values {
			logTimestamp := logData[0]
			logTimestampDigits, _ := strconv.ParseInt(logTimestamp, 10, 64)
			logTimestampTime := time.Unix(0, logTimestampDigits)
			logPod := result.Stream.Pod
			logMessage := logData[1]
			logNamespace := result.Stream.Namespace
			logNode := result.Stream.NodeName

			// Save non-empty logs to the result list
			tmpMsg := strings.ReplaceAll(logMessage, "\n", "")
			tmpMsg = strings.ReplaceAll(tmpMsg, " ", "")
			if tmpMsg != "" {
				resultList = append(resultList, LokiLogData{Namespace: logNamespace, Timestamp: logTimestampTime, Text: logMessage, Pod: logPod, Node: logNode})
			}
		}
	}
	return
}
