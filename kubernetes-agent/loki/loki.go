package loki

import (
	"context"
	"github.com/carlmjohnson/requests"
	"log"
	"strconv"
	"strings"
	"time"
)

type LokiServer struct {
	Endpoint string
}

const HEALTH_API = "/ready"
const RANGE_QUERY_API = "/loki/api/v1/query_range"
const LOG_QUERY = "{namespace=~\"%s\"}"

func (loki *LokiServer) Query(queryStr string, StartTime string, EndTime string) LogQueryResponseBody {
	var response LogQueryResponseBody
	err := requests.URL(loki.Endpoint+RANGE_QUERY_API).Param("query", queryStr).Param("start", StartTime).Param("end", EndTime).Param("direction", "forward").Param("limit", "5000").ToJSON(&response).Fetch(context.Background())
	if err != nil {
		log.Output(2, "Failed to query loki server: "+loki.Endpoint)
		panic(err)
	}
	return response
}

func (loki *LokiServer) Verify() {
	var response string
	err := requests.URL(loki.Endpoint + HEALTH_API).ToString(&response).Fetch(context.Background())
	if err != nil || strings.ReplaceAll(response, "\n", "") != "ready" {
		log.Output(2, "Loki server is not ready: "+response)
		panic(err)
	}
}

func (loki *LokiServer) GetLogData(namespace string, StartTime time.Time, EndTime time.Time) []LokiLogData {
	var resultList []LokiLogData
	queryStr := FormatQueryWithNamespaces(LOG_QUERY, namespace)
	queryResult := loki.Query(queryStr, StartTime.Format(time.RFC3339), EndTime.Format(time.RFC3339))
	for _, result := range queryResult.Data.Result {
		for _, logData := range result.Values {
			logTimestamp := logData[0]
			logTimestampDigits, _ := strconv.ParseInt(logTimestamp, 10, 64)
			logTimestampTime := time.Unix(0, logTimestampDigits)
			logPod := result.Stream.Pod
			logMessage := logData[1]
			logNamespace := result.Stream.Namespace

			// Save to the result list
			resultList = append(resultList, LokiLogData{Namespace: logNamespace, Timestamp: logTimestampTime, Text: logMessage, Pod: logPod})
		}
	}
	return ProcessMultiLines(&resultList)
}
