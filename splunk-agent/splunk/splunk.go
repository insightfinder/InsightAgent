package splunk

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/insightfinder/splunk-agent/configs"
	"github.com/sirupsen/logrus"
)

// Service is the Splunk REST API client.
type Service struct {
	cfg        configs.SplunkConfig
	httpClient *http.Client
}

// NewService creates and returns a configured Splunk service.
func NewService(cfg configs.SplunkConfig) *Service {
	skipVerify := !cfg.VerifySSL
	return &Service{
		cfg: cfg,
		httpClient: &http.Client{
			Timeout: time.Duration(cfg.QueryTimeout) * time.Second,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: skipVerify},
			},
		},
	}
}

// setAuth applies token auth (Splunk Cloud) or Basic Auth (Enterprise).
func (s *Service) setAuth(req *http.Request) {
	if s.cfg.Token != "" {
		req.Header.Set("Authorization", "Splunk "+s.cfg.Token)
	} else {
		req.SetBasicAuth(s.cfg.Username, s.cfg.Password)
	}
}

// SearchRange runs an SPL query for the given [start, end) window and returns
// matching events. The caller should not include time modifiers in the SPL —
// this method passes earliest_time / latest_time as API parameters.
func (s *Service) SearchRange(query configs.QueryConfig, start, end time.Time) ([]SplunkEvent, error) {
	sid, err := s.createJob(query.Query, start, end)
	if err != nil {
		return nil, fmt.Errorf("create job: %w", err)
	}

	if err := s.waitForJob(sid); err != nil {
		return nil, fmt.Errorf("wait job: %w", err)
	}

	events, err := s.fetchResults(sid, query.MaxResults)
	if err != nil {
		return nil, fmt.Errorf("fetch results: %w", err)
	}
	return events, nil
}

// createJob submits a Splunk search job and returns the SID.
func (s *Service) createJob(spl string, start, end time.Time) (string, error) {
	form := url.Values{}
	form.Set("search", spl)
	form.Set("output_mode", "json")
	form.Set("earliest_time", strconv.FormatInt(start.Unix(), 10))
	form.Set("latest_time", strconv.FormatInt(end.Unix(), 10))

	endpoint := s.cfg.ServerURL + "/services/search/jobs"
	req, err := http.NewRequest("POST", endpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return "", err
	}
	s.setAuth(req)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusCreated {
		return "", fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(body))
	}

	var jr jobResponse
	if err := json.Unmarshal(body, &jr); err != nil {
		return "", fmt.Errorf("parse SID: %w", err)
	}
	if jr.SID == "" {
		return "", fmt.Errorf("empty SID in response")
	}
	return jr.SID, nil
}

// waitForJob polls until the Splunk job isDone or the service timeout elapses.
func (s *Service) waitForJob(sid string) error {
	endpoint := fmt.Sprintf("%s/services/search/jobs/%s?output_mode=json", s.cfg.ServerURL, sid)
	deadline := time.Now().Add(time.Duration(s.cfg.QueryTimeout) * time.Second)

	for time.Now().Before(deadline) {
		req, err := http.NewRequest("GET", endpoint, nil)
		if err != nil {
			return err
		}
		s.setAuth(req)

		resp, err := s.httpClient.Do(req)
		if err != nil {
			return err
		}
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		var status jobStatusResponse
		if err := json.Unmarshal(body, &status); err != nil {
			return fmt.Errorf("parse job status: %w", err)
		}
		if len(status.Entry) == 0 {
			return fmt.Errorf("no entry for SID %s", sid)
		}
		content := status.Entry[0].Content
		logrus.Debugf("Job %s progress: %.0f%%", sid, content.DoneProgress*100)
		if content.IsDone {
			return nil
		}
		time.Sleep(500 * time.Millisecond)
	}
	return fmt.Errorf("timed out waiting for job %s", sid)
}

// fetchResults retrieves all result events for a completed job.
func (s *Service) fetchResults(sid string, maxResults int) ([]SplunkEvent, error) {
	endpoint := fmt.Sprintf(
		"%s/services/search/jobs/%s/results?output_mode=json&count=%d",
		s.cfg.ServerURL, sid, maxResults,
	)

	req, err := http.NewRequest("GET", endpoint, nil)
	if err != nil {
		return nil, err
	}
	s.setAuth(req)

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("results fetch status %d: %s", resp.StatusCode, string(body))
	}

	var results searchResults
	if err := json.Unmarshal(body, &results); err != nil {
		return nil, fmt.Errorf("parse results: %w", err)
	}
	return results.Results, nil
}

// ParseTimestamp converts the Splunk _time string to Unix milliseconds.
// Splunk returns _time as ISO-8601 (e.g. "2026-04-10T10:00:01.000+00:00")
// or as an epoch float string.
func ParseTimestamp(raw string) int64 {
	formats := []string{
		time.RFC3339Nano,
		"2006-01-02T15:04:05.999999999-07:00",
		"2006-01-02T15:04:05-07:00",
		"2006-01-02T15:04:05.000Z",
		"2006-01-02T15:04:05Z",
	}
	for _, f := range formats {
		if t, err := time.Parse(f, raw); err == nil {
			return t.UnixMilli()
		}
	}
	// Fallback: epoch seconds as float
	if f, err := strconv.ParseFloat(raw, 64); err == nil {
		return int64(f * 1000)
	}
	logrus.Warnf("splunk: could not parse _time %q, using now", raw)
	return time.Now().UnixMilli()
}
