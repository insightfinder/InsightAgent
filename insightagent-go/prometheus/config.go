package prometheus

import (
	"encoding/json"
	"fmt"
	"github.com/araddon/dateparse"
	"github.com/bigkevmcd/go-configparser"
	. "insightagent-go/insightfinder"
	"os"
	"regexp"
	"strings"
	"time"
)

const SECTION_NAME = "prometheus"

type Config struct {
	ApiUrl      string
	User        string
	Password    string
	VerifyCerts bool
	Proxies     map[string]string

	HisStartTime time.Time
	HisEndTime   time.Time

	ComponentField         string
	DefaultComponentName   string
	InstanceFields         []string
	InstanceConnector      string
	DynamicHostField       string
	DeviceFields           []string
	MetricNameFields       []string
	InstanceWhitelistRegex *regexp.Regexp

	Queries []PrometheusQuery
}

func getPrometheusConfig(p *configparser.ConfigParser) *Config {
	var prometheusUri = GetConfigString(p, SECTION_NAME, "prometheus_uri", true)
	var user = GetConfigString(p, SECTION_NAME, "user", true)
	var password = GetConfigString(p, SECTION_NAME, "password", true)
	var verifyCerts = GetConfigBool(p, SECTION_NAME, "verify_certs", false, false)

	var hisTimeRangeStr = GetConfigString(p, SECTION_NAME, "his_time_range", false)
	var hisStartTime = time.Time{}
	var hisEndTime = time.Time{}

	if hisTimeRangeStr != "" {
		times := strings.Split(hisTimeRangeStr, ",")
		if len(times) != 2 {
			panic(fmt.Sprintf("Invalid his_time_range: %s", hisTimeRangeStr))
		}

		startTime, err := dateparse.ParseAny(times[0])
		if err != nil {
			panic(fmt.Sprintf("Invalid time format in his_time_range: %s", hisTimeRangeStr))
		}
		endTime, err := dateparse.ParseAny(times[1])
		if err != nil {
			panic(fmt.Sprintf("Invalid time format in his_time_range: %s", hisTimeRangeStr))
		}
		hisStartTime = startTime
		hisEndTime = endTime
	}

	var prometheusQueryStr = GetConfigString(p, SECTION_NAME, "prometheus_query", false)
	var prometheusQueryJsonFile = GetConfigString(p, SECTION_NAME, "prometheus_query_json", false)
	var metricBatchSize = GetConfigInt(p, SECTION_NAME, "prometheus_query_metric_batch_size", false, 0)
	var batchMetricFilterRegex = GetConfigString(p, SECTION_NAME, "batch_metric_filter_regex", false)

	var queries = make([]PrometheusQuery, 0)
	if prometheusQueryStr != "" {
		qs := SplitString(prometheusQueryStr, ";")
		for _, query := range qs {
			// If query has :, the format is metric:instance:query
			if strings.Contains(query, ":") {
				parts := strings.Split(query, ":")
				if len(parts) != 3 {
					panic(fmt.Sprintf("Invalid query format: %s. Ex: metric:instancs:query", query))
				}
				instances := SplitString(parts[1], ",")
				queries = append(queries, PrometheusQuery{
					MetricName:             parts[0],
					Query:                  parts[2],
					BatchSize:              metricBatchSize,
					BatchMetricFilterRegex: batchMetricFilterRegex,
					InstanceFields:         instances,
				})
			} else {
				queries = append(queries, PrometheusQuery{
					MetricName:             "",
					Query:                  query,
					BatchSize:              metricBatchSize,
					BatchMetricFilterRegex: batchMetricFilterRegex,
					InstanceFields:         make([]string, 0),
				})
			}
		}
	}

	if prometheusQueryJsonFile != "" {
		// Read from json file
		jsonFilePath := AbsFilePath("conf.d/" + prometheusQueryJsonFile)
		data, err := os.ReadFile(jsonFilePath)
		if err != nil {
			panic(fmt.Sprintf("Failed to open prometheus query json file: %s %v", jsonFilePath, err))
		}
		fileQuery := make([]PrometheusQuery, 0)
		json.Unmarshal(data, &fileQuery)

		queries = append(queries, fileQuery...)
	}

	var agentHttpProxy = GetConfigString(p, SECTION_NAME, "agent_http_proxy", false)
	var agentHttpsProxy = GetConfigString(p, SECTION_NAME, "agent_https_proxy", false)
	var proxies = make(map[string]string)
	if agentHttpProxy != "" {
		proxies["http"] = agentHttpProxy
	}
	if agentHttpsProxy != "" {
		proxies["https"] = agentHttpsProxy
	}

	var componentField = GetConfigString(p, SECTION_NAME, "component_field", false)
	var defaultComponentName = GetConfigString(p, SECTION_NAME, "default_component_name", false)

	var instanceFields = make([]string, 0)
	var instanceFieldStr = GetConfigString(p, SECTION_NAME, "instance_field", false)
	if instanceFieldStr != "" {
		instanceFields = SplitString(instanceFieldStr, ",")
	}
	var instanceConnector = GetConfigString(p, SECTION_NAME, "instance_connector", false)
	if instanceConnector == "" {
		instanceConnector = "-"
	}
	var instanceWhitelistRegex *regexp.Regexp
	var instanceWhitelist = GetConfigString(p, SECTION_NAME, "instance_whitelist", false)
	if instanceWhitelist != "" {
		instanceWhitelistRegex = regexp.MustCompile(instanceWhitelist)
	}

	var deviceFieldStr = GetConfigString(p, SECTION_NAME, "device_field", false)
	var deviceFields = make([]string, 0)
	if deviceFieldStr != "" {
		deviceFields = SplitString(deviceFieldStr, ",")
	}

	var dynamicHostField = GetConfigString(p, SECTION_NAME, "dynamic_host_field", false)

	var metricNameFields = make([]string, 0)
	var metricNameFieldsStr = GetConfigString(p, SECTION_NAME, "metrics_name_field", false)
	if metricNameFieldsStr != "" {
		metricNameFields = SplitString(metricNameFieldsStr, ",")
	}

	/*
		var data_format = insight.GetConfigString(p, SECTION_NAME, "data_format", false)
		var project_field = insight.GetConfigString(p, SECTION_NAME, "project_field", false)

		var timestamp_field = insight.GetConfigString(p, SECTION_NAME, "timestamp_field", false)
		var target_timestamp_timezone = insight.GetConfigString(p, SECTION_NAME, "target_timestamp_timezone", false)
		var timestamp_format = insight.GetConfigString(p, SECTION_NAME, "timestamp_format", false)
		var timezone = insight.GetConfigString(p, SECTION_NAME, "timezone", false)
		var timestamp_format = insight.GetConfigString(p, SECTION_NAME, "timestamp_format", false)
	*/
	config := Config{
		ApiUrl:      BuildCompleteURL(prometheusUri, "api/v1/"),
		User:        user,
		Password:    password,
		VerifyCerts: verifyCerts,
		Proxies:     proxies,

		HisStartTime: hisStartTime,
		HisEndTime:   hisEndTime,

		ComponentField:       componentField,
		DefaultComponentName: defaultComponentName,

		InstanceFields:         instanceFields,
		InstanceConnector:      instanceConnector,
		DynamicHostField:       dynamicHostField,
		InstanceWhitelistRegex: instanceWhitelistRegex,
		DeviceFields:           deviceFields,
		MetricNameFields:       metricNameFields,

		Queries: queries,
	}

	return &config
}
