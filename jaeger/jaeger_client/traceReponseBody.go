package jaeger_client

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
	StartTime int64 `json:"startTime"`
	Duration  int   `json:"duration"`
	Tags      []struct {
		Key   string `json:"key"`
		Type  string `json:"type"`
		Value string `json:"value"`
	} `json:"tags"`
	Logs      []interface{} `json:"logs"`
	ProcessID string        `json:"processID"`
	Warnings  interface{}   `json:"warnings"`
}
