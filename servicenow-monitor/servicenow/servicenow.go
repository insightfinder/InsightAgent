package servicenow

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	config "github.com/insightfinder/servicenow-monitor/configs"
	"github.com/sirupsen/logrus"
)

const INCIDENT_API = "/api/now/table/incident"

type Client struct {
	instance         config.ServiceNowInstance
	httpClient       *http.Client
	shortDescription string
	deleteAfterCheck bool
	maxRetries       int
	retryInterval    time.Duration
}

type incident struct {
	SysID            string `json:"sys_id"`
	Number           string `json:"number"`
	ShortDescription string `json:"short_description"`
}

type incidentResponse struct {
	Result incident `json:"result"`
}

func NewClient(instance config.ServiceNowInstance, cfg config.ServiceNowConfig) *Client {
	tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: !cfg.VerifySSL}}
	return &Client{
		instance:         instance,
		httpClient:       &http.Client{Transport: tr, Timeout: time.Duration(cfg.TimeoutSec) * time.Second},
		shortDescription: cfg.ShortDescription,
		deleteAfterCheck: cfg.DeleteAfterCheck,
		maxRetries:       cfg.MaxRetries,
		retryInterval:    time.Duration(cfg.RetryIntervalSec) * time.Second,
	}
}

// HealthCheck creates a dummy incident, fetches it back by sys_id and
// verifies the returned record matches what was created.
func (c *Client) HealthCheck() error {
	var created *incident
	err := c.retry("create incident", func() (err error) {
		created, err = c.createIncident()
		return err
	})
	if err != nil {
		return fmt.Errorf("create incident: %v", err)
	}
	logrus.Infof("[%s] Created incident %s (sys_id=%s)", c.instance.Name, created.Number, created.SysID)

	var fetched *incident
	err = c.retry("retrieve incident "+created.Number, func() (err error) {
		fetched, err = c.getIncident(created.SysID)
		if err == nil && (fetched.SysID != created.SysID || fetched.Number != created.Number) {
			err = fmt.Errorf("retrieved incident mismatch: created %s/%s, got %s/%s",
				created.Number, created.SysID, fetched.Number, fetched.SysID)
		}
		return err
	})
	if err != nil {
		return fmt.Errorf("retrieve incident %s: %v", created.Number, err)
	}
	logrus.Infof("[%s] Retrieved incident %s successfully", c.instance.Name, fetched.Number)

	if c.deleteAfterCheck {
		if err := c.deleteIncident(created.SysID); err != nil {
			// Create and retrieve worked, so the instance is healthy; only warn.
			logrus.Warnf("[%s] Failed to delete incident %s: %v", c.instance.Name, created.Number, err)
		} else {
			logrus.Infof("[%s] Deleted incident %s", c.instance.Name, created.Number)
		}
	}
	return nil
}

// retry runs fn up to maxRetries times, sleeping retryInterval between
// failed attempts, and returns the last error if every attempt fails.
func (c *Client) retry(action string, fn func() error) error {
	var err error
	for attempt := 1; attempt <= c.maxRetries; attempt++ {
		if err = fn(); err == nil {
			return nil
		}
		logrus.Warnf("[%s] %s attempt %d/%d failed: %v", c.instance.Name, action, attempt, c.maxRetries, err)
		if attempt < c.maxRetries {
			time.Sleep(c.retryInterval)
		}
	}
	return fmt.Errorf("failed after %d attempts: %v", c.maxRetries, err)
}

func (c *Client) createIncident() (*incident, error) {
	body, _ := json.Marshal(map[string]string{
		"short_description": c.shortDescription,
		"description":       fmt.Sprintf("Automated health check created by InsightFinder at %s", time.Now().UTC().Format(time.RFC3339)),
		"urgency":           "3",
		"impact":            "3",
	})
	var resp incidentResponse
	if err := c.do(http.MethodPost, INCIDENT_API, body, http.StatusCreated, &resp); err != nil {
		return nil, err
	}
	if resp.Result.SysID == "" || resp.Result.Number == "" {
		return nil, fmt.Errorf("response missing sys_id/number")
	}
	return &resp.Result, nil
}

func (c *Client) getIncident(sysID string) (*incident, error) {
	var resp incidentResponse
	if err := c.do(http.MethodGet, INCIDENT_API+"/"+sysID, nil, http.StatusOK, &resp); err != nil {
		return nil, err
	}
	return &resp.Result, nil
}

func (c *Client) deleteIncident(sysID string) error {
	return c.do(http.MethodDelete, INCIDENT_API+"/"+sysID, nil, http.StatusNoContent, nil)
}

func (c *Client) do(method, path string, body []byte, wantStatus int, out interface{}) error {
	req, err := http.NewRequest(method, c.instance.URL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.SetBasicAuth(c.instance.Username, c.instance.Password)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != wantStatus {
		return fmt.Errorf("unexpected status %d: %s", resp.StatusCode, truncate(string(respBody), 300))
	}
	if out != nil {
		// A hibernating developer instance answers 200 with an HTML page, so a
		// JSON decode failure is treated as a failed check.
		if err := json.Unmarshal(respBody, out); err != nil {
			return fmt.Errorf("invalid JSON response: %v: %s", err, truncate(string(respBody), 300))
		}
	}
	return nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
