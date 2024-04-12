package loki

import (
	"bytes"
	"context"
	"fmt"
	"github.com/carlmjohnson/requests"
	"gopkg.in/yaml.v3"
	"log/slog"
	"strconv"
	"strings"
	"time"
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
		slog.Error("Failed to query loki server: " + loki.Endpoint)
		slog.Error(err.Error())
	}
	return response
}

func (loki *LokiServer) Initialize() {

	// Connectivity check
	var response string
	err := requests.URL(loki.Endpoint+HEALTH_API).BasicAuth(loki.Username, loki.Password).ToString(&response).Fetch(context.Background())
	if err != nil || strings.ReplaceAll(response, "\n", "") != "OK" {
		slog.Error("Loki server is not ready: " + response)
		slog.Error(err.Error())
	} else {
		slog.Info("Loki server response: " + response)
	}

	// Setup config
	LokiConfig := loki.getConfig()
	loki.MaxEntriesLimitPerQuery = LokiConfig.LimitsConfig.MaxEntriesLimitPerQuery
}

func (loki *LokiServer) getConfig() LogConfigResponseBody {
	var configResponse bytes.Buffer
	err := requests.URL(loki.Endpoint + CONFIG_API).ToBytesBuffer(&configResponse).Fetch(context.Background())
	if err != nil {
		slog.Error("Failed to get config from Loki server.")
	} else {
		slog.Info("Read config from Loki server successfully.")
	}

	// Decode response to yaml struct
	config := yaml.NewDecoder(&configResponse)
	var configYaml LogConfigResponseBody
	err = config.Decode(&configYaml)
	if err != nil {
		slog.Error("Failed to decode config from Loki server.")
		fmt.Print(configResponse)
	}
	return configYaml
}

func (loki *LokiServer) GetLogData(namespace string, podList []string, StartTime time.Time, EndTime time.Time) []LokiLogData {
	var resultList []*LokiLogData
	for _, pod := range podList {
		queryStr := FormatQuery(LOG_QUERY, namespace, pod)
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
				logContainer := result.Stream.Container

				// Save non-empty logs to the result list
				tmpMsg := strings.ReplaceAll(logMessage, "\n", "")
				tmpMsg = strings.ReplaceAll(tmpMsg, " ", "")
				if tmpMsg != "" {
					resultList = append(resultList, &LokiLogData{Namespace: logNamespace, Timestamp: logTimestampTime, Text: logMessage, Pod: logPod, Container: logContainer, Node: logNode})
				}
			}
		}
	}
	return ProcessMultiLines(resultList)
}
