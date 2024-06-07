package jaeger_client

import (
	"encoding/json"
	"fmt"
)

type TraceResponseBody struct {
	Data []TraceData `json:"data"`
}

type TraceData struct {
	TraceID  string      `json:"traceID"`
	Spans    []Span      `json:"spans"`
	Warnings interface{} `json:"warnings"`
}
type Span struct {
	TraceID       string `json:"traceID"`
	SpanID        string `json:"spanID"`
	OperationName string `json:"operationName"`
	References    []struct {
		RefType string `json:"refType"`
		TraceID string `json:"traceID"`
		SpanID  string `json:"spanID"`
	} `json:"references"`
	StartTime int64                   `json:"startTime"`
	Duration  int                     `json:"duration"`
	Tags      []Tag                   `json:"tags"`
	TagMap    map[string]StringOrBool `json:"tagsMap"`
	Logs      []interface{}           `json:"logs"`
	ProcessID string                  `json:"processID"`
	Warnings  interface{}             `json:"warnings"`
}

type Tag struct {
	Key   string       `json:"key"`
	Type  string       `json:"type"`
	Value StringOrBool `json:"value"`
}

type StringOrBool string

func (sob *StringOrBool) UnmarshalJSON(data []byte) error {
	var strVal string
	if err := json.Unmarshal(data, &strVal); err == nil {
		*sob = StringOrBool(strVal)
		return nil
	}

	var boolVal bool
	if err := json.Unmarshal(data, &boolVal); err == nil {
		// Convert boolean to string
		if boolVal {
			*sob = "true"
		} else {
			*sob = "false"
		}
		return nil
	}

	return fmt.Errorf("value cannot be converted to StringOrBool: %v", data)
}
