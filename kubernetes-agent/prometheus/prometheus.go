package prometheus

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/carlmjohnson/requests"
	"log"
	"strconv"
	"time"
)

const (
	CONFIG_API = "/api/v1/status/config"
	QUERY_API  = "/api/v1/query_range"
)

const (
	CPU_METRIC_QUERY         = "sum(rate(container_cpu_usage_seconds_total{namespace=~\"%s\",container!='POD',container!='',pod!=''}[3m])) by (pod,namespace,instance)"
	MEMORY_METRIC_QUERY      = "sum(container_memory_working_set_bytes{namespace=~\"%s\",container!='POD',container!='',pod!=''}) by (pod,namespace,instance)"
	DISK_READ_METRIC_QUERY   = "sum(rate(container_fs_reads_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance)"
	DISK_WRITE_METRIC_QUERY  = "sum(rate(container_fs_writes_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance)"
	NETWORK_IN_METRIC_QUERY  = "sum(rate(container_network_receive_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance)"
	NETWORK_OUT_METRIC_QUERY = "sum(rate(container_network_transmit_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance)"
)

type PrometheusServer struct {
	// Constants
	EndPoint    string
	UserName    string
	Password    string
	VerifyCerts string
	CACerts     string
	ClientCert  string
	ClientKey   string

	// Vars
	IsBasicAuth bool
}

func (p PrometheusServer) Verify() bool {

	// Must have EndPoint
	if p.EndPoint == "" {
		return false
	}

	if p.UserName != "" && p.Password != "" {
		p.IsBasicAuth = true
	} else {
		p.IsBasicAuth = false
	}

	// Test connection by getting configuration.
	ConfigResponseBody := ConfigResponseBody{}
	requests.URL(p.EndPoint + CONFIG_API).ToJSON(&ConfigResponseBody).Fetch(context.Background())
	return ConfigResponseBody.Status != "success"
}

func (p PrometheusServer) Query(QueryStr string, StartTime time.Time, EndTime time.Time) QueryResponseBody {
	StartTimeStr := fmt.Sprintf("%.3f", float64(StartTime.UnixMilli())/1000)
	EndTimeStr := fmt.Sprintf("%.3f", float64(EndTime.UnixMilli())/1000)
	ResponseBody := QueryResponseBody{}
	err := requests.URL(p.EndPoint+QUERY_API).Param("query", QueryStr).Param("start", StartTimeStr).Param("end", EndTimeStr).Param("step", "60").ToJSON(&ResponseBody).Fetch(context.Background())

	if err != nil {
		log.Println("Failed to query: ", QueryStr)
		log.Println(err.Error())
		return ResponseBody
	} else {
		return ResponseBody
	}
}

func (p PrometheusServer) GetMetricData(Type string, namespaceFilter string, StartTime time.Time, EndTime time.Time) []PromMetricData {
	var QueryStr string
	var promMetricData []PromMetricData

	switch Type {
	case "CPU":
		QueryStr = CPU_METRIC_QUERY
	case "Memory":
		QueryStr = MEMORY_METRIC_QUERY
	case "DiskRead":
		QueryStr = DISK_READ_METRIC_QUERY
	case "DiskWrite":
		QueryStr = DISK_WRITE_METRIC_QUERY
	case "NetworkIn":
		QueryStr = NETWORK_IN_METRIC_QUERY
	case "NetworkOut":
		QueryStr = NETWORK_OUT_METRIC_QUERY
	}
	QueryStr = FormatQueryWithNamespaces(QueryStr, namespaceFilter)

	QueryResult := p.Query(QueryStr, StartTime, EndTime)
	for _, Data := range QueryResult.Data.Result {
		NameSpace := Data.Metric.Namespace
		Pod := Data.Metric.Pod
		Node := Data.Metric.Node
		metrics := make([]Metric, 0)
		for _, ValueSet := range Data.Values {
			var Timestamp float64
			var Value string
			json.Unmarshal(ValueSet[0], &Timestamp)
			json.Unmarshal(ValueSet[1], &Value)
			valueFloat64, _ := strconv.ParseFloat(Value, 64)
			metrics = append(metrics, Metric{int64(Timestamp * 1000), valueFloat64})
		}
		promMetricData = append(promMetricData, PromMetricData{Type, NameSpace, Pod, Node, metrics})
	}
	return promMetricData
}
