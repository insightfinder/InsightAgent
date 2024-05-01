package jaeger_client

import "github.com/carlmjohnson/requests"
import "time"

type JaegerClient struct {
	Endpoint string
}

func (jc *JaegerClient) QueryTrace(startTime time.Time, endTime time.Time, service string, operation string, tags *map[string]string) {
	params := make(map[string][]string)
	responseBody := TraceResponseBody{}
	requests.URL(jc.Endpoint).Params(params).ToJSON(&responseBody)

}

func (jc *JaegerClient) GetTraces() {

}
