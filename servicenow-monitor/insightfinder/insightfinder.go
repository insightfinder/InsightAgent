package insightfinder

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"

	config "github.com/insightfinder/servicenow-monitor/configs"
	"github.com/sirupsen/logrus"
)

const (
	METRIC_DATA_API     = "/api/v2/metric-data-receive"
	PROJECT_ENDPOINT    = "/api/v1/check-and-add-custom-project"
	DATA_TYPE           = "Metric"
	INSIGHT_AGENT_TYPE  = "Custom"
	HTTP_RETRY_TIMES    = 3
	HTTP_RETRY_INTERVAL = 5 // seconds
)

func NewService(cfg config.InsightFinderConfig) *Service {
	tr := &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}
	return &Service{
		config:     cfg,
		httpClient: &http.Client{Transport: tr, Timeout: 180 * time.Second},
	}
}

// CreateProjectIfNotExist checks for the project and creates it when missing.
func (s *Service) CreateProjectIfNotExist() error {
	exists, err := s.IsProjectExist()
	if err != nil {
		return err
	}
	if exists {
		return nil
	}
	if err := s.CreateProject(); err != nil {
		return err
	}
	exists, err = s.IsProjectExist()
	if err != nil {
		return err
	}
	if !exists {
		return fmt.Errorf("project '%s' still missing after create", s.config.ProjectName)
	}
	return nil
}

func (s *Service) IsProjectExist() (bool, error) {
	logrus.Infof("Checking if project '%s' exists in InsightFinder", s.config.ProjectName)

	body, err := s.postProjectRequest(CheckAndAddCustomProjectRequest{
		Operation:   "check",
		UserName:    s.config.UserName,
		LicenseKey:  s.config.LicenseKey,
		ProjectName: s.config.ProjectName,
		SystemName:  s.config.SystemName,
	})
	if err != nil {
		return false, fmt.Errorf("project check failed: %v", err)
	}

	var checkResponse CheckAndAddCustomProjectResponse
	if err := json.Unmarshal(body, &checkResponse); err != nil {
		return false, fmt.Errorf("failed to decode project check response: %v: %s", err, string(body))
	}
	if !checkResponse.IsSuccess {
		return false, fmt.Errorf("project check failed: %s", checkResponse.Message)
	}

	if checkResponse.IsProjectExist {
		logrus.Infof("Project '%s' exists in InsightFinder", s.config.ProjectName)
	} else {
		logrus.Infof("Project '%s' does not exist in InsightFinder", s.config.ProjectName)
	}
	return checkResponse.IsProjectExist, nil
}

func (s *Service) CreateProject() error {
	logrus.Infof("Creating project '%s' (system '%s') in InsightFinder", s.config.ProjectName, s.config.SystemName)

	body, err := s.postProjectRequest(CheckAndAddCustomProjectRequest{
		Operation:        "create",
		UserName:         s.config.UserName,
		LicenseKey:       s.config.LicenseKey,
		ProjectName:      s.config.ProjectName,
		SystemName:       s.config.SystemName,
		InstanceType:     s.config.InstanceType,
		ProjectCloudType: s.config.CloudType,
		DataType:         DATA_TYPE,
		InsightAgentType: INSIGHT_AGENT_TYPE,
		SamplingInterval: s.config.SamplingInterval,
	})
	if err != nil {
		return fmt.Errorf("failed to create project: %v", err)
	}

	var resp CheckAndAddCustomProjectResponse
	if err := json.Unmarshal(body, &resp); err == nil && !resp.IsSuccess {
		return fmt.Errorf("failed to create project: %s", resp.Message)
	}
	logrus.Infof("Project '%s' created successfully in InsightFinder", s.config.ProjectName)
	return nil
}

// postProjectRequest calls the check-and-add-custom-project API. With the
// agent-type: Stream header, "check" reads the JSON body while "create" needs
// the fields as query params too, so both are sent (same as positron-agent).
func (s *Service) postProjectRequest(request CheckAndAddCustomProjectRequest) ([]byte, error) {
	payload, err := json.Marshal(request)
	if err != nil {
		return nil, err
	}
	var fields map[string]interface{}
	_ = json.Unmarshal(payload, &fields)
	params := url.Values{}
	for k, v := range fields {
		params.Set(k, fmt.Sprint(v))
	}
	endpoint := s.config.ServerURL + PROJECT_ENDPOINT + "?" + params.Encode()
	req, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("agent-type", "Stream")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status %d: %s", resp.StatusCode, string(body))
	}
	return body, nil
}

// SendMetrics sends metrics to the project using the v2 metric API.
func (s *Service) SendMetrics(metrics []MetricData) error {
	if len(metrics) == 0 {
		return nil
	}

	instanceDataMap := make(map[string]InstanceData)
	var minTimestamp, maxTimestamp int64

	for i, metric := range metrics {
		timestamp := alignTimestamp(metric.Timestamp, s.config.SamplingInterval)
		if i == 0 || timestamp < minTimestamp {
			minTimestamp = timestamp
		}
		if timestamp > maxTimestamp {
			maxTimestamp = timestamp
		}

		instanceData, exists := instanceDataMap[metric.InstanceName]
		if !exists {
			var imStr string
			if metric.ComponentName != "" {
				imBytes, _ := json.Marshal(map[string]string{"cn": metric.ComponentName})
				imStr = string(imBytes)
			}
			instanceData = InstanceData{
				InstanceName:        metric.InstanceName,
				InstanceMetadataStr: imStr,
				DataInTimestampMap:  make(map[int64]DataInTimestamp),
			}
		}

		dataInTimestamp := instanceData.DataInTimestampMap[timestamp]
		dataInTimestamp.TimeStamp = timestamp
		for metricName, value := range metric.Data {
			dataInTimestamp.MetricDataPoints = append(dataInTimestamp.MetricDataPoints, MetricDataPoint{
				MetricName: metricName,
				Value:      value,
			})
		}
		instanceData.DataInTimestampMap[timestamp] = dataInTimestamp
		instanceDataMap[metric.InstanceName] = instanceData
	}

	payload := IFMetricPostRequestPayload{
		LicenseKey: s.config.LicenseKey,
		UserName:   s.config.UserName,
		Data: MetricDataReceivePayload{
			ProjectName:      s.config.ProjectName,
			UserName:         s.config.UserName,
			SystemName:       s.config.SystemName,
			InstanceDataMap:  instanceDataMap,
			MinTimestamp:     minTimestamp,
			MaxTimestamp:     maxTimestamp,
			InsightAgentType: INSIGHT_AGENT_TYPE,
			SamplingInterval: strconv.Itoa(s.config.SamplingInterval),
			CloudType:        s.config.CloudType,
		},
	}

	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal metrics payload: %v", err)
	}
	logrus.Debugf("Metric payload: %s", string(jsonPayload))

	var lastErr error
	for attempt := 1; attempt <= HTTP_RETRY_TIMES; attempt++ {
		lastErr = s.postMetricPayload(jsonPayload)
		if lastErr == nil {
			logrus.Infof("Successfully sent metrics to InsightFinder (instances: %d)", len(instanceDataMap))
			return nil
		}
		logrus.Warnf("Attempt %d/%d failed: %v", attempt, HTTP_RETRY_TIMES, lastErr)
		if attempt < HTTP_RETRY_TIMES {
			time.Sleep(HTTP_RETRY_INTERVAL * time.Second)
		}
	}
	return fmt.Errorf("failed to send metrics after %d attempts: %v", HTTP_RETRY_TIMES, lastErr)
}

func (s *Service) postMetricPayload(jsonPayload []byte) error {
	req, err := http.NewRequest(http.MethodPost, s.config.ServerURL+METRIC_DATA_API, bytes.NewReader(jsonPayload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("status %d: %s", resp.StatusCode, string(body))
	}
	logrus.Debugf("InsightFinder response: %s", string(body))
	return nil
}

// alignTimestamp aligns an epoch-ms timestamp to the sampling interval.
func alignTimestamp(timestamp int64, samplingInterval int) int64 {
	if samplingInterval == 0 {
		return timestamp
	}
	samplingIntervalMs := int64(samplingInterval) * 1000
	return (timestamp / samplingIntervalMs) * samplingIntervalMs
}
