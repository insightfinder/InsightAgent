package prometheus

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"github.com/bigkevmcd/go-configparser"
	"github.com/go-resty/resty/v2"
	"github.com/rs/zerolog/log"
	"github.com/samber/lo"
	. "insightagent-go/insightfinder"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

var STRIP_PORT, _ = regexp.Compile("(.+):\\d+")

type PrometheusQuery struct {
	MetricName             string   `json:"metric_name"`
	Query                  string   `json:"query"`
	BatchSize              int      `json:"metric_batch_size"`
	BatchMetricFilterRegex string   `json:"batch_metric_filter_regex"`
	InstanceFields         []string `json:"instance_fields"`
	DeviceFields           []string `json:"device_fields"`
}

func createClient(config *Config) *resty.Client {
	client := resty.New()

	if !config.VerifyCerts {
		client.SetTLSClientConfig(&tls.Config{InsecureSkipVerify: true})
	}

	if IsDebugMode {
		//client.SetDebug(true)
	}

	if config.User != "" && config.Password != "" {
		client.SetBasicAuth(config.User, config.Password)
	}
	for _, value := range config.Proxies {
		client.SetProxy(value)
	}

	client.RetryCount = 3
	client.RetryWaitTime = 10

	return client
}

func getDataValues(data map[string]interface{}, keys []string) []string {
	var values []string
	for _, key := range keys {
		if value, ok := data[key]; ok {
			val := value.(string)
			if val != "" {
				values = append(values, val)
			}
		}
	}
	return values
}

func processPrometheusMessages(
	ifConfig *IFConfig,
	config *Config,
	query *PrometheusQuery,
	collectTime time.Time,
	message interface{}) *DataMessage {

	msg := message.(map[string]interface{})
	if msg == nil {
		return nil
	}

	var metricData = msg["metric"].(map[string]interface{})
	var valueData = msg["value"].([]interface{})
	if metricData == nil || valueData == nil || len(valueData) <= 1 {
		log.Warn().Msgf("invalid message, ignored, %v", msg)
		return nil
	}

	// Get the component name
	componentName := ""
	if config.ComponentField != "" {
		vals := getDataValues(metricData, []string{config.ComponentField})
		if len(vals) > 0 {
			componentName = vals[0]
		}
	}
	if componentName == "" {
		componentName = config.DefaultComponentName
	}

	// Get the instance field with device info if available
	instance := "Application"
	instanceFields := query.InstanceFields
	if len(instanceFields) == 0 {
		instanceFields = config.InstanceFields
	}
	if len(instanceFields) > 0 {
		vals := getDataValues(metricData, instanceFields)
		if len(vals) > 0 {
			vals = lo.Map(vals, func(val string, _ int) string {
				// Remove the port from the host (.*):\d+
				return STRIP_PORT.ReplaceAllString(val, "$1")
			})
			instance = strings.Join(vals, config.InstanceConnector)
		}
	}
	if config.InstanceWhitelistRegex != nil &&
		!config.InstanceWhitelistRegex.MatchString(instance) {
		return nil
	}

	device := ""
	deviceFields := config.DeviceFields
	if len(query.DeviceFields) > 0 {
		deviceFields = query.DeviceFields
	}
	if len(deviceFields) > 0 {
		vals := getDataValues(metricData, deviceFields)
		if len(vals) > 0 {
			device = strings.Join(vals, config.InstanceConnector)
		}
	}

	fullInstance := MakeSafeInstanceString(instance, device)

	hostId := ""
	if config.DynamicHostField != "" {
		vals := getDataValues(metricData, []string{config.DynamicHostField})
		if len(vals) > 0 {
			hostId = STRIP_PORT.ReplaceAllString(vals[0], "$1")
			hostId = MakeSafeInstanceString(hostId, "")
		}
	}

	// Get the metric name field
	var dataField = query.MetricName
	if dataField == "" {
		var fields = config.MetricNameFields
		if len(fields) == 0 {
			fields = []string{"__name__"}
			vals := getDataValues(metricData, fields)
			if len(vals) > 0 {
				dataField = strings.Join(vals, "_")
			}
		}
	}

	// Get the timestamp and align it to the sampling interval
	timestamp := int64(valueData[0].(float64))
	if len(strconv.FormatInt(timestamp, 10)) == 10 {
		timestamp = timestamp * 1000
	}
	if config.TimezoneOffsetSeconds != 0 {
		timestamp = timestamp + int64(config.TimezoneOffsetSeconds*1000)
	}
	timestamp = AlignTimestamp(timestamp, ifConfig.SamplingInterval*1000)

	dataValue := valueData[1].(string)

	return &DataMessage{
		Timestamp:     fmt.Sprintf("%.0f", timestamp),
		ComponentName: componentName,
		Instance:      fullInstance,
		MetricName:    dataField,
		HostId:        hostId,
		Value:         dataValue,
	}
}

func queryPrometheusMessages(
	ifConfig *IFConfig,
	config *Config,
	query *PrometheusQuery,
	collectTime time.Time,
	params map[string]string,
) *[]DataMessage {
	defer func() {
		if r := recover(); r != nil {
			log.Error().Msgf("Failed to query prometheus messages %v", r)
		}
	}()

	var endpoint = BuildCompleteURL(config.ApiUrl, "query")
	log.Info().Msgf("Start querying prometheus message %s %v", endpoint, params)

	client := createClient(config)
	resp, err := client.R().SetQueryParams(params).Post(endpoint)
	if err != nil {
		panic(fmt.Sprintf("Failed to query prometheus messages: %v", err))
	}

	if resp.StatusCode() != 200 {
		panic(fmt.Sprintf("Failed to query prometheus messages: %s", resp.String()))
	}

	var result map[string]interface{}
	err = json.Unmarshal(resp.Body(), &result)
	if err != nil {
		panic(fmt.Sprintf("Error parsing response: %v", err.Error()))
	}

	if result["status"] != "success" {
		panic(fmt.Sprintf("Failed to query prometheus messages: %s", resp.String()))
	}

	data := result["data"].(map[string]interface{})

	var dataResult = make([]DataMessage, 0)
	if data["resultType"] != "vector" {
		log.Warn().Msgf("Unsupported result type: %s", data["resultType"])
		return &dataResult
	}

	messages := data["result"].([]interface{})
	log.Info().Msgf("Prometheus query found %d messages", len(messages))

	for _, item := range messages {
		mdata := processPrometheusMessages(ifConfig, config, query, collectTime, item)
		if mdata != nil {
			dataResult = append(dataResult, *mdata)
		}
	}

	return &dataResult
}

func queryPrometheusLabels(config *Config) []string {
	var endpoint = BuildCompleteURL(config.ApiUrl, "label/__name__/values")
	log.Debug().Msgf("Start querying prometheus labels at %s", endpoint)

	client := createClient(config)
	resp, err := client.R().Get(endpoint)
	if err != nil {
		panic(fmt.Sprintf("Failed to query prometheus labels: %v", err))
	}

	if resp.StatusCode() != 200 {
		panic(fmt.Sprintf("Failed to query prometheus labels: %s", resp.String()))
	}

	var result map[string]interface{}
	err = json.Unmarshal(resp.Body(), &result)
	if err != nil {
		panic(fmt.Sprintf("Error parsing response: %v", err.Error()))
	}

	if result["status"] != "success" {
		panic(fmt.Sprintf("Failed to query prometheus labels: %s", resp.String()))
	}

	var labels []string
	for _, label := range result["data"].([]interface{}) {
		labels = append(labels, label.(string))
	}

	return labels
}

func runPrometheusQuery(
	ifConfig *IFConfig,
	config *Config,
	collectTime time.Time) {
	timestamp := AlignTimestamp(collectTime.UnixMilli(), ifConfig.SamplingInterval*1000)

	log.Info().Msgf("Collecting prometheus data at time %d", timestamp)

	// Run queries with the given timestamp and wait for all results
	results := make(chan *[]DataMessage)
	var wg sync.WaitGroup
	for _, query := range config.Queries {
		log.Info().Msgf("Running query: %s", query.Query)

		metricBatchList := make([][]string, 0)

		if query.BatchSize > 0 {
			allMetricList := queryPrometheusLabels(config)
			metricList := allMetricList
			if query.BatchMetricFilterRegex != "" {
				metricList = lo.Filter(allMetricList, func(item string, index int) bool {
					matched, _ := regexp.MatchString(query.BatchMetricFilterRegex, item)
					return matched
				})
			}
			log.Info().Msgf("Metrics found %d and filtered %d}", len(allMetricList), len(metricList))
			log.Debug().Msgf("Metrics filtered: %v}", metricList)

			if len(metricList) == 0 {
				metricBatchList = MakeBuckets(metricList, query.BatchSize)
			} else {
				metricBatchList = append(metricBatchList, make([]string, 0))
			}
		} else {
			metricBatchList = append(metricBatchList, make([]string, 0))
		}

		for _, metricBatch := range metricBatchList {
			queryStr := query.Query
			mql := map[string]string{
				"time": strconv.FormatInt(timestamp/1000, 10),
			}

			if len(metricBatch) > 0 {
				metricQueries := lo.Map(metricBatch, func(metric string, _ int) string {
					return fmt.Sprintf(`%s"%s"}`, queryStr, metric)
				})
				mql["query"] = fmt.Sprintf(queryStr, strings.Join(metricQueries, " or "))
			} else {
				mql["query"] = queryStr
			}

			wg.Add(1)
			go func(q map[string]string, results chan<- *[]DataMessage) {
				defer wg.Done()
				results <- queryPrometheusMessages(ifConfig, config, &query, collectTime, q)
			}(mql, results)
		}
	}

	go func() {
		wg.Wait()
		close(results)
	}()

	// Get all results an
	var dataResult = make([]DataMessage, 0)

	for result := range results {
		for _, mdata := range *result {
			dataResult = append(dataResult, mdata)
		}
	}

	if len(dataResult) > 0 {
		SendMetricData(ifConfig, &dataResult)
	}
}

func Collect(ifConfig *IFConfig,
	configFile *configparser.ConfigParser,
	samplingTime time.Time) {
	defer func() {
		if r := recover(); r != nil {
			log.Error().Msgf("Failed to collect prometheus data %v", r)
		}
	}()

	config := getPrometheusConfig(configFile)
	configLog := *config
	configLog.Password = "********"

	log.Info().Msg("Starting Prometheus collector")
	log.Info().Msgf("Prometheus config: %+v", configLog)

	if !config.HisStartTime.IsZero() && !config.HisEndTime.IsZero() {
		// run historical query
		interval := time.Duration(ifConfig.SamplingInterval) * time.Second
		for t := config.HisStartTime; t.Before(config.HisEndTime); t = t.Add(interval) {
			runPrometheusQuery(ifConfig, config, t)
		}
	} else {
		runPrometheusQuery(ifConfig, config, samplingTime)
	}
}
