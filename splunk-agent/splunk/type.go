package splunk

// SplunkEvent is one result row returned by the Splunk search REST API.
// All fields (including _raw, _time, host, source, sourcetype, index, and
// any extra fields Splunk returns) are preserved so they can be forwarded
// as structured JSON.
type SplunkEvent map[string]interface{}

// GetString returns the string value of key, or "" if absent or non-string.
func (e SplunkEvent) GetString(key string) string {
	v, ok := e[key]
	if !ok {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return s
}

// searchResults is the top-level JSON shape of a Splunk results response.
type searchResults struct {
	Results []SplunkEvent `json:"results"`
}

// jobResponse is returned by POST /services/search/jobs.
type jobResponse struct {
	SID string `json:"sid"`
}

// jobStatusResponse is used to poll job completion.
type jobStatusResponse struct {
	Entry []struct {
		Content struct {
			IsDone       bool    `json:"isDone"`
			DoneProgress float64 `json:"doneProgress"`
		} `json:"content"`
	} `json:"entry"`
}
