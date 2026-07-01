package iflib

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

const maxMetricPayloadBytes = 10 * 1024 * 1024 // 10 MB — InsightFinder hard limit

// MetricDataPoint is a single metric name/value pair inside a timestamp bucket.
type MetricDataPoint struct {
	Metric string  `json:"m"`
	Value  float64 `json:"v"`
}

// MetricTimestamp groups data points at one moment in time.
type MetricTimestamp struct {
	Timestamp        int64             `json:"t"`
	MetricDataPoints []MetricDataPoint `json:"metricDataPointSet"`
}

// MetricInstance contains one instance's time-series data for the v2 payload.
type MetricInstance struct {
	InstanceName  string                     `json:"in"`
	ComponentName string                     `json:"cn,omitempty"`
	Zone          string                     `json:"z,omitempty"`
	IP            string                     `json:"i,omitempty"`
	DataInTime    map[string]MetricTimestamp `json:"dit"` // key = ms timestamp as string
}

// metricPayloadData is the inner envelope sent to /api/v2/metric-data-receive.
type metricPayloadData struct {
	ProjectName      string                    `json:"projectName"`
	UserName         string                    `json:"userName"`
	SystemName       string                    `json:"systemName"`
	InsightAgentType string                    `json:"iat"`
	CloudType        string                    `json:"ct"`
	SamplingInterval string                    `json:"si"`
	MinTimestamp     int64                     `json:"minTimestamp"`
	MaxTimestamp     int64                     `json:"maxTimestamp"`
	InstanceDataMap  map[string]MetricInstance `json:"idm"`
}

type metricPayload struct {
	LicenseKey string            `json:"licenseKey"`
	UserName   string            `json:"userName"`
	Data       metricPayloadData `json:"data"`
}

// MetricRecord is a single time-series observation for one instance, ready to send.
type MetricRecord struct {
	InstanceName  string
	ComponentName string
	// Timestamp in milliseconds. Values < 1e12 are treated as seconds and converted.
	Timestamp int64
	Zone      string
	IP        string
	// Metrics maps metric name → value (non-numeric values are skipped).
	Metrics map[string]float64
}

// SendMetricsOptions configures a SendMetrics call.
type SendMetricsOptions struct {
	// AgentType identifies the collection agent (default: "Custom").
	AgentType string
	// CloudType identifies the deployment type (default: "OnPremise").
	CloudType string
	// SamplingInterval is the collection period in seconds (default: 60).
	SamplingInterval int
	// AlignTimestamps rounds timestamps down to sampling-interval boundaries.
	AlignTimestamps bool
}

// SendMetrics sends metric data to a project using the v2 metric-data-receive API.
func (c *Client) SendMetrics(ctx context.Context, projectName, systemName string, records []MetricRecord, opts *SendMetricsOptions) error {
	if len(records) == 0 {
		return nil
	}

	agentType, cloudType, samplingInterval := resolveMetricOpts(opts)

	instanceDataMap := make(map[string]MetricInstance, len(records))
	var minTS, maxTS int64

	for i, rec := range records {
		ts := rec.Timestamp
		if ts < 1e12 {
			ts *= 1000
		}
		if opts != nil && opts.AlignTimestamps {
			ts = alignTimestamp(ts, int64(samplingInterval))
		}

		if i == 0 || ts < minTS {
			minTS = ts
		}
		if i == 0 || ts > maxTS {
			maxTS = ts
		}

		inst, ok := instanceDataMap[rec.InstanceName]
		if !ok {
			inst = MetricInstance{
				InstanceName:  rec.InstanceName,
				ComponentName: rec.ComponentName,
				Zone:          rec.Zone,
				IP:            rec.IP,
				DataInTime:    make(map[string]MetricTimestamp),
			}
		}

		tsKey := strconv.FormatInt(ts, 10)
		mt := inst.DataInTime[tsKey]
		mt.Timestamp = ts
		for name, val := range rec.Metrics {
			mt.MetricDataPoints = append(mt.MetricDataPoints, MetricDataPoint{Metric: name, Value: val})
		}
		inst.DataInTime[tsKey] = mt
		instanceDataMap[rec.InstanceName] = inst
	}

	payload := metricPayload{
		LicenseKey: c.licenseKey,
		UserName:   c.userName,
		Data: metricPayloadData{
			ProjectName:      projectName,
			UserName:         c.userName,
			SystemName:       systemName,
			InsightAgentType: agentType,
			CloudType:        cloudType,
			SamplingInterval: strconv.Itoa(samplingInterval),
			MinTimestamp:     minTS,
			MaxTimestamp:     maxTS,
			InstanceDataMap:  instanceDataMap,
		},
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal metric payload: %w", err)
	}
	if len(data) > maxMetricPayloadBytes {
		return fmt.Errorf("payload %d bytes exceeds %d byte limit; use SendMetricsChunked", len(data), maxMetricPayloadBytes)
	}

	// Use doWithRetry directly to avoid re-marshaling the already-built bytes.
	body, status, err := c.doWithRetry(ctx, "POST", c.serverURL+"/api/v2/metric-data-receive", data, func(req *http.Request) {
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-User-Name", c.userName)
		req.Header.Set("X-API-Key", c.licenseKey)
	})
	if err != nil {
		return err
	}
	if status != 200 {
		return apiErr(status, body)
	}
	return nil
}

// SendMetricsChunked splits a large metric record slice into chunks and sends each chunk.
// Use when your dataset exceeds the 10 MB per-request limit.
func (c *Client) SendMetricsChunked(ctx context.Context, projectName, systemName string, records []MetricRecord, chunkSize int, opts *SendMetricsOptions) error {
	if chunkSize <= 0 {
		chunkSize = 1000
	}
	for i := 0; i < len(records); i += chunkSize {
		end := i + chunkSize
		if end > len(records) {
			end = len(records)
		}
		if err := c.SendMetrics(ctx, projectName, systemName, records[i:end], opts); err != nil {
			return fmt.Errorf("chunk %d: %w", i/chunkSize, err)
		}
		if end < len(records) {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
	return nil
}

// MetricQuery defines parameters for a metric time-series data query.
type MetricQuery struct {
	ProjectName  string
	InstanceName string
	MetricList   []string
	StartTime    int64 // milliseconds
	EndTime      int64 // milliseconds
}

// MetricQueryPoint is one data point returned by QueryMetrics.
type MetricQueryPoint struct {
	InstanceName string
	MetricName   string
	Timestamp    int64
	Value        float64
}

// QueryMetrics retrieves metric time-series data from a project.
func (c *Client) QueryMetrics(ctx context.Context, q MetricQuery) ([]MetricQueryPoint, error) {
	metricsJSON, _ := json.Marshal(q.MetricList)

	params := url.Values{}
	params.Set("projectName", q.ProjectName)
	params.Set("customerName", c.userName)
	params.Set("instanceName", q.InstanceName)
	params.Set("metricList", string(metricsJSON))
	params.Set("startTime", strconv.FormatInt(q.StartTime, 10))
	params.Set("endTime", strconv.FormatInt(q.EndTime, 10))

	body, status, err := c.doJSON(ctx, "GET", "/api/v1/metricdataquery-external", nil, params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	// Response: map[instanceName]map[metricName][][timestamp, value]
	var raw map[string]map[string][]any
	if err := decodeJSON(body, &raw); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	var results []MetricQueryPoint
	for instanceName, metrics := range raw {
		for metricName, points := range metrics {
			for _, pt := range points {
				pair, ok := pt.([]any)
				if !ok || len(pair) < 2 {
					continue
				}
				ts, _ := pair[0].(float64)
				val, _ := pair[1].(float64)
				results = append(results, MetricQueryPoint{
					InstanceName: instanceName,
					MetricName:   metricName,
					Timestamp:    int64(ts),
					Value:        val,
				})
			}
		}
	}
	return results, nil
}

// GetMetricNames returns the list of metric names available for a project.
func (c *Client) GetMetricNames(ctx context.Context, projectName string) ([]string, error) {
	params := url.Values{}
	params.Set("projectName", projectName)
	params.Set("customerName", c.userName)

	body, status, err := c.doJSON(ctx, "GET", "/api/v1/metricmetadata-external", nil, params)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, apiErr(status, body)
	}

	var result struct {
		MetricList []string `json:"metricList"`
	}
	if err := decodeJSON(body, &result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	return result.MetricList, nil
}

// alignTimestamp rounds a millisecond timestamp down to the nearest sampling interval boundary.
func alignTimestamp(tsMs, samplingIntervalSeconds int64) int64 {
	intervalMs := samplingIntervalSeconds * 1000
	return (tsMs / intervalMs) * intervalMs
}

func resolveMetricOpts(opts *SendMetricsOptions) (agentType, cloudType string, samplingInterval int) {
	agentType = "Custom"
	cloudType = "OnPremise"
	samplingInterval = 60
	if opts == nil {
		return
	}
	if opts.AgentType != "" {
		agentType = opts.AgentType
	}
	if opts.CloudType != "" {
		cloudType = opts.CloudType
	}
	if opts.SamplingInterval > 0 {
		samplingInterval = opts.SamplingInterval
	}
	return
}
