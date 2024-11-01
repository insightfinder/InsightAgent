package response

type QueryResponseModel struct {
	Results QueryResponseResult `json:"results"`
}

type QueryResponseResult struct {
	A QueryResponseResultDetail `json:"A"`
}

type QueryResponseResultDetail struct {
	Status int                  `json:"status"`
	Frames []QueryResponseFrame `json:"frames"`
}

type QueryResponseFrame struct {
	Schema QueryResponseSchema `json:"schema"`
	Data   QueryResponseData   `json:"data"`
}

type QueryResponseSchema struct {
	RefId  string               `json:"refId"`
	Meta   QueryResponseMeta    `json:"meta"`
	Fields []QueryResponseField `json:"fields"`
}

type QueryResponseMeta struct {
	Type                string                  `json:"type"`
	TypeVersion         []int                   `json:"typeVersion"`
	Custom              QueryResponseCustomMeta `json:"custom"`
	ExecutedQueryString string                  `json:"executedQueryString,omitempty"`
}

type QueryResponseCustomMeta struct {
	ResultType string `json:"resultType"`
}

type QueryResponseField struct {
	Name     string                `json:"name"`
	Type     string                `json:"type"`
	TypeInfo QueryResponseTypeInfo `json:"typeInfo"`
	Config   QueryResponseConfig   `json:"config"`
	Labels   map[string]string     `json:"labels,omitempty"` // pointer to allow omission if nil
}

type QueryResponseTypeInfo struct {
	Frame string `json:"frame"`
}

type QueryResponseConfig struct {
	Interval          int    `json:"interval,omitempty"`
	DisplayNameFromDS string `json:"displayNameFromDS,omitempty"`
}

type QueryResponseData struct {
	Values [][]float64 `json:"values"`
}
