package loki

import (
	"bytes"
	"context"
	"github.com/carlmjohnson/requests"
	"gopkg.in/yaml.v2"
	"log"
	"strconv"
	"time"
)

type LokiServer struct {
	Endpoint string
	Config   LokiConfig
}

const CONFIG_API = "/config"
const RANGE_QUERY_API = "/loki/api/v1/query_range"
const LOG_QUERY = "{namespace=~\"%s\", pod=\"%s\"}"

func (loki *LokiServer) Query(queryStr string, StartTime string, EndTime string) LogQueryResponseBody {
	var response LogQueryResponseBody
	err := requests.URL(loki.Endpoint+RANGE_QUERY_API).Param("query", queryStr).Param("start", StartTime).Param("end", EndTime).Param("direction", "forward").Param("limit", strconv.Itoa(loki.Config.LimitsConfig.MaxEntriesLimitPerQuery)).ToJSON(&response).Fetch(context.Background())
	if err != nil {
		log.Output(2, "Failed to query loki server: "+loki.Endpoint)
		panic(err)
	}
	return response
}

func (loki *LokiServer) Initialize() {
	var buf bytes.Buffer
	err := requests.URL(loki.Endpoint + CONFIG_API).ToBytesBuffer(&buf).Fetch(context.Background())
	if err != nil {
		log.Output(2, "Loki server is not ready.")
		panic(err)
	}
	err = yaml.Unmarshal(buf.Bytes(), &loki.Config)
	if err != nil {
		log.Fatalf("Failed to read config from Loki.")
	}

}

func (loki *LokiServer) GetLogData(namespace string, podList []string, StartTime time.Time, EndTime time.Time) []LokiLogData {
	var resultList []LokiLogData

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

				// Save to the result list
				resultList = append(resultList, LokiLogData{Namespace: logNamespace, Timestamp: logTimestampTime, Text: logMessage, Pod: logPod, Node: logNode})
			}
		}
	}
	return ProcessMultiLines(&resultList)
}
