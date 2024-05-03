package jaeger_client

import (
	"context"
	"github.com/carlmjohnson/requests"
	"log/slog"
	"net/url"
	"strconv"
	"sync"
)
import "time"

type JaegerClient struct {
	Endpoint    string
	Username    string
	Password    string
	StartTime   time.Time
	EndTime     time.Time
	Tags        *map[string]string
	Service     string
	Operation   string
	Limit       int
	Step        time.Duration
	MaxDuration string
	MinDuration string
}

func NewJaegerClient(endpoint string) JaegerClient {
	return JaegerClient{Endpoint: endpoint}
}

func (jc *JaegerClient) QueryTrace(ctx context.Context, results chan<- *Span, startTime time.Time, endTime time.Time) {
	responseBody := TraceResponseBody{}
	startTimeStr := strconv.FormatInt(startTime.UnixMilli()*1000, 10)
	endTimeStr := strconv.FormatInt(endTime.UnixMilli()*1000, 10)
	params := url.Values{}
	params.Add("service", jc.Service)
	params.Add("start", startTimeStr)
	params.Add("end", endTimeStr)
	params.Add("limit", strconv.Itoa(jc.Limit))

	if jc.Operation != "" {
		params.Add("operation", jc.Operation)
	}
	if jc.MinDuration != "" {
		params.Add("minDuration", jc.MinDuration)
	}
	if jc.MaxDuration != "" {
		params.Add("maxDuration", jc.MaxDuration)
	}
	queryEndpoint := jc.Endpoint + "/api/traces"
	err := requests.URL(queryEndpoint).Params(params).ToJSON(&responseBody).Fetch(ctx)
	if err != nil {
		slog.Error("Error fetching traces", err)
	}

	// Send data back to the channel
	for _, trace := range responseBody.Data {
		for _, span := range trace.Spans {
			results <- &span
		}
	}
}

func (jc *JaegerClient) GetTraces(ctx context.Context, chn chan<- *Span) {

	var queryWg sync.WaitGroup

	rangeStartTime := jc.StartTime
	rangeEndTime := jc.StartTime.Add(jc.Step)

	for rangeStartTime.Before(jc.EndTime) && rangeEndTime.Before(jc.EndTime) {

		// Query for traces in the current range
		queryWg.Add(1)
		go func() {
			defer queryWg.Done()
			jc.QueryTrace(ctx, chn, rangeStartTime, rangeEndTime)
		}()

		// Move to next Tick
		rangeStartTime = rangeStartTime.Add(jc.Step)
		rangeEndTime = rangeEndTime.Add(jc.Step)
		if rangeEndTime.After(jc.EndTime) {
			rangeEndTime = jc.EndTime
		}
	}
	queryWg.Wait()

}
