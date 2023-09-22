package prometheus

import (
	"encoding/json"
)

type ConfigResponseBody struct {
	Status string `json:"status"`
	Data   struct {
		Yaml string `json:"yaml"`
	} `json:"data"`
}

type ValueSet struct {
	TimeStamp float64
	Value     string
}

type QueryResponseBody struct {
	Status string `json:"status"`
	Error  string `json:"error"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Metric struct {
				Namespace    string `json:"namespace"`
				Pod          string `json:"pod"`
				Container    string `json:"container"`
				NodeInstance string `json:"instance"`
				Node         string `json:"node"`
			} `json:"metric"`
			Values [][]json.RawMessage `json:"values"`
		} `json:"result"`
	} `json:"data"`
}

type Metric struct {
	TimeStamp int64
	Value     float64
}

type PromMetricData struct {
	Type      string // CPU, Memory, NetworkIn,NetworkOut , DiskRead, DiskWrite
	NameSpace string
	Pod       string
	Node      string
	Data      []Metric
}
