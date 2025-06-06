package ruckus

import (
	"bytes"
	"net/http"
)

// Helper function for GET requests with session management
func (s *Service) get(url string) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	return s.executeRequest(req)
}

// Helper function for POST requests with session management
func (s *Service) post(url string, body []byte) (*http.Response, error) {
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	return s.executeRequest(req)
}
