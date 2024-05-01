package jaeger_client

type TraceResponseBody struct {
	Data []struct {
		TraceID string `json:"traceID"`
		Spans   []struct {
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
		} `json:"spans"`
		Processes struct {
			P1 struct {
				ServiceName string `json:"serviceName"`
				Tags        []struct {
					Key   string `json:"key"`
					Type  string `json:"type"`
					Value string `json:"value"`
				} `json:"tags"`
			} `json:"p1"`
			P2 struct {
				ServiceName string `json:"serviceName"`
				Tags        []struct {
					Key   string `json:"key"`
					Type  string `json:"type"`
					Value string `json:"value"`
				} `json:"tags"`
			} `json:"p2,omitempty"`
			P3 struct {
				ServiceName string `json:"serviceName"`
				Tags        []struct {
					Key   string `json:"key"`
					Type  string `json:"type"`
					Value string `json:"value"`
				} `json:"tags"`
			} `json:"p3,omitempty"`
			P4 struct {
				ServiceName string `json:"serviceName"`
				Tags        []struct {
					Key   string `json:"key"`
					Type  string `json:"type"`
					Value string `json:"value"`
				} `json:"tags"`
			} `json:"p4,omitempty"`
		} `json:"processes"`
		Warnings interface{} `json:"warnings"`
	} `json:"data"`
	Total  int         `json:"total"`
	Limit  int         `json:"limit"`
	Offset int         `json:"offset"`
	Errors interface{} `json:"errors"`
}
