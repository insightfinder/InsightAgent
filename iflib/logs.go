package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
)

// LogEntry is a single log event.
type LogEntry struct {
	Timestamp     int64   `json:"timestamp"`
	Tag           string  `json:"tag"`
	Data          any     `json:"data"`
	ComponentName string  `json:"componentName,omitempty"`
	IPAddress     string  `json:"ipAddress,omitempty"`
}

// SendLogsOptions configures a SendLogs call.
type SendLogsOptions struct {
	// AgentType identifies the log collector (default: "LogStreaming").
	AgentType string
	// InstanceName is the source host identifier (default: "default").
	InstanceName string
}

// SendLogs sends log events to a project using the v1 customprojectrawdata API.
func (c *Client) SendLogs(ctx context.Context, projectName string, entries []LogEntry, opts *SendLogsOptions) error {
	if len(entries) == 0 {
		return nil
	}

	agentType, instanceName := resolveLogOpts(opts)

	metricDataJSON, err := json.Marshal(entries)
	if err != nil {
		return fmt.Errorf("marshal log entries: %w", err)
	}

	form := url.Values{}
	form.Set("projectName", projectName)
	form.Set("instanceName", instanceName)
	form.Set("agentType", agentType)
	form.Set("metricData", string(metricDataJSON))

	body, status, err := c.doForm(ctx, "POST", "/api/v1/customprojectrawdata", form)
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}

// SendLogsChunked splits a large entry slice and sends each chunk individually.
// Default chunk size is 5000 entries.
func (c *Client) SendLogsChunked(ctx context.Context, projectName string, entries []LogEntry, chunkSize int, opts *SendLogsOptions) error {
	if chunkSize <= 0 {
		chunkSize = 5000
	}
	for i := 0; i < len(entries); i += chunkSize {
		end := i + chunkSize
		if end > len(entries) {
			end = len(entries)
		}
		if err := c.SendLogs(ctx, projectName, entries[i:end], opts); err != nil {
			return fmt.Errorf("chunk %d: %w", i/chunkSize, err)
		}
	}
	return nil
}

func resolveLogOpts(opts *SendLogsOptions) (agentType, instanceName string) {
	agentType = "LogStreaming"
	instanceName = "default"
	if opts == nil {
		return
	}
	if opts.AgentType != "" {
		agentType = opts.AgentType
	}
	if opts.InstanceName != "" {
		instanceName = opts.InstanceName
	}
	return
}
