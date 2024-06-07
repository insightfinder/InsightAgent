package jaeger_client

import (
	"context"
	"log/slog"
	"net/url"
	"strconv"
	"sync"
	"time"

	"github.com/carlmjohnson/requests"
)

type JaegerClient struct {
	Endpoint      string
	Username      string
	Password      string
	StartTime     time.Time
	EndTime       time.Time
	Tags          *map[string]string
	Service       string
	Operation     string
	Limit         int
	Step          time.Duration
	MaxDuration   string
	MinDuration   string
	InstanceTags  []string
	ComponentTags []string
}

func (jc *JaegerClient) QueryTrace(startTime time.Time, endTime time.Time, spanChan chan *Span) {
	responseBody := TraceResponseBody{}
	startTimeStr := strconv.FormatInt(startTime.UnixMilli()*1000, 10)
	endTimeStr := strconv.FormatInt(endTime.UnixMilli()*1000, 10)
	params := url.Values{}
	params.Add("service", jc.Service)
	params.Add("start", startTimeStr)
	params.Add("end", endTimeStr)
	params.Add("limit", strconv.Itoa(jc.Limit))

	if jc.Tags != nil {
		tagsParam := ""
		for key, value := range *jc.Tags {
			tagsParam += key + "=" + value + " "
		}

		if tagsParam != "" {
			params.Add("tags", tagsParam)
		}
	}

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
	err := requests.URL(queryEndpoint).Params(params).ToJSON(&responseBody).Fetch(context.Background())
	if err != nil {
		slog.Error("Error fetching traces", err)
	}
	// Send data back to the channel
	for _, trace := range responseBody.Data {
		for _, span := range trace.Spans {

			// Create TagsMap from Tags
			span.TagMap = make(map[string]StringOrBool)
			for tag := range span.Tags {
				span.TagMap[span.Tags[tag].Key] = span.Tags[tag].Value
			}
			spanChan <- &span
		}
	}
}

func (jc *JaegerClient) StreamTraces(spanChan chan *Span) {

	rangeStartTime := jc.StartTime
	rangeEndTime := jc.StartTime.Add(jc.Step)

	wg := sync.WaitGroup{}

	for rangeStartTime.Before(jc.EndTime) && rangeEndTime.Before(jc.EndTime) {

		wg.Add(1)
		// Query Trace
		go func(startTime time.Time, endTime time.Time) {
			jc.QueryTrace(startTime, endTime, spanChan)
			wg.Done()
		}(rangeStartTime, rangeEndTime)

		// Move to next Tick
		rangeStartTime = rangeStartTime.Add(jc.Step)
		rangeEndTime = rangeEndTime.Add(jc.Step)
		if rangeEndTime.After(jc.EndTime) {
			rangeEndTime = jc.EndTime
		}
	}
	wg.Wait()
}
