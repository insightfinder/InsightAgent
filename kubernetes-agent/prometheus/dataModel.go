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
				Namespace string `json:"namespace"`
				Pod       string `json:"pod"`
				Container string `json:"container"`
			} `json:"metric"`
			Values [][]json.RawMessage `json:"values"`
		} `json:"result"`
	} `json:"data"`
}

type Metric struct {
	TimeStamp float64
	Value     string
}

type PromMetricData struct {
	NameSpace string
	Pod       string
	Container string
	Data      []Metric
}
