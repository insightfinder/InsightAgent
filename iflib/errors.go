package iflib

import "fmt"

// APIError represents a non-2xx HTTP response from the InsightFinder API.
type APIError struct {
	StatusCode int
	Message    string // extracted from the response body when available
	Body       string // raw response body
}

func (e *APIError) Error() string {
	if e.Message != "" {
		return fmt.Sprintf("API error %d: %s", e.StatusCode, e.Message)
	}
	body := e.Body
	if len(body) > 200 {
		body = body[:200] + "…"
	}
	if body != "" {
		return fmt.Sprintf("API error %d: %s", e.StatusCode, body)
	}
	return fmt.Sprintf("API error %d", e.StatusCode)
}

// tryExtractMessage attempts to pull a human-readable message out of a JSON body.
// Returns the message if found, otherwise returns "".
func tryExtractMessage(body []byte) string {
	var envelope struct {
		Message string `json:"message"`
		Msg     string `json:"msg"`
		Error   string `json:"error"`
	}
	if err := decodeJSON(body, &envelope); err != nil {
		return ""
	}
	if envelope.Message != "" {
		return envelope.Message
	}
	if envelope.Msg != "" {
		return envelope.Msg
	}
	return envelope.Error
}

// apiErr builds an APIError, trying to extract a human-readable message from the body.
func apiErr(statusCode int, body []byte) *APIError {
	return &APIError{
		StatusCode: statusCode,
		Message:    tryExtractMessage(body),
		Body:       string(body),
	}
}
