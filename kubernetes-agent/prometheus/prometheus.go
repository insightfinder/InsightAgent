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
	POD_CPU_CORES_METRIC_QUERY                = "sum(rate(container_cpu_usage_seconds_total{namespace=~\"%s\",container!='POD',container!='',pod!=''}[3m])) by (pod,namespace,instance)"
	POD_CPU_USAGE_PERCENTAGE                  = "sum(rate(container_cpu_usage_seconds_total{ namespace=~\"%s\",image!=\"\", container_name!=\"POD\"}[3m])) by (pod,namespace,instance) / sum(container_spec_cpu_quota{image!=\"\", container_name!=\"POD\"}/container_spec_cpu_period{ image!=\"\", container_name!=\"POD\"}) by  (pod,namespace,instance) * 100"
	POD_MEMORY_METRIC_QUERY                   = "sum(container_memory_working_set_bytes{namespace=~\"%s\",container!='POD',container!='',pod!=''}) by (pod,namespace,instance)  / 1024 / 1024"
	POD_MEMORY_USAGE_PERCENTAGE_METRIC_QUERY  = "100 *    sum(container_memory_working_set_bytes{namespace=~\"%s\",image!=\"\", container_name!=\"POD\"}) by (instance, pod, namespace) /  sum(container_spec_memory_limit_bytes{image!=\"\", container_name!=\"POD\"} > 0) by (instance, pod, namespace)"
	POD_DISK_READ_METRIC_QUERY                = "sum(rate(container_fs_reads_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance) / 1024 / 1024"
	POD_DISK_WRITE_METRIC_QUERY               = "sum(rate(container_fs_writes_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance) / 1024 / 1024"
	POD_NETWORK_IN_METRIC_QUERY               = "sum(rate(container_network_receive_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance) / 1024 / 1024"
	POD_NETWORK_OUT_METRIC_QUERY              = "sum(rate(container_network_transmit_bytes_total{namespace=~\"%s\",container!='POD',pod!=''}[3m])) by (pod, namespace,instance) / 1024 / 1024"
	POD_PROCESSES_QUERY                       = "sum (container_processes{namespace=~\"%s\"}) by (pod,namespace,instance)"
	NODE_CPU_USAGE_PERCENTAGE_METRIC_QUERY    = "(sum(rate(node_cpu_seconds_total{mode=~\"user|system\"}[2m])) by (node) / sum(rate(node_cpu_seconds_total[2m])) by (node)) * 100"
	NODE_MEMORY_USAGE_MB_METRIC_QUERY         = "sum (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) by (node) / 1024 / 1024"
	NODE_MEMORY_USAGE_PERCENTAGE_METRIC_QUERY = "sum((1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))) by (node) * 100"
	NODE_DISK_USAGE_PERCENTAGE_METRIC_QUERY   = "sum(( (node_filesystem_size_bytes{mountpoint=\"/\"} - node_filesystem_avail_bytes{mountpoint=\"/\"}) / node_filesystem_size_bytes{mountpoint=\"/\"}) * 100) by (node)"
	NODE_DISK_READ_RATE_METRIC_QUERY          = "sum(rate(node_disk_read_bytes_total[2m])) by (node) / 1024 / 1024"
	NODE_DISK_WRITE_RATE_METRIC_QUERY         = "sum(rate(node_disk_written_bytes_total[2m])) by (node) / 1024 / 1024"
	NODE_NETWORK_IN_RATE_METRIC_QUERY         = "sum(rate(node_network_receive_bytes_total{device!~\"lo\"}[2m])) by (node) / 1024 / 1024"
	NODE_NETWORK_OUT_RATE_METRIC_QUERY        = "sum(rate(node_network_transmit_bytes_total{device!~\"lo\"}[2m])) by (node) / 1024 / 1024"
	NODE_PROCESSES_METRIC_QUERY               = "sum (node_procs_running) by (node)"
	NODE_BLOCKED_PROCESSES_METRIC_QUERY       = "sum (node_procs_blocked) by (node)"
	PVC_CAPACITY_METRIC_QUERY                 = "sum(kubelet_volume_stats_capacity_bytes{namespace=~\"%s\"}) by (persistentvolumeclaim,namespace) / 1024 / 1024"
	PVC_USAGE_METRIC_QUERY                    = "sum(kubelet_volume_stats_used_bytes{namespace=~\"%s\"}) by (persistentvolumeclaim,namespace) / 1024 / 1024"
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
}

func (p *PrometheusServer) Initialize() bool {

	// Must have EndPoint
	if p.EndPoint == "" {
		return false
	}

	// Test connection by getting configuration.
	ConfigResponseBody := ConfigResponseBody{}
	requests.URL(p.EndPoint+CONFIG_API).BasicAuth(p.UserName, p.Password).ToJSON(&ConfigResponseBody).Fetch(context.Background())
	return ConfigResponseBody.Status != "success"
}

func (p *PrometheusServer) Query(QueryStr string, StartTime time.Time, EndTime time.Time) QueryResponseBody {
	StartTimeStr := fmt.Sprintf("%.3f", float64(StartTime.UnixMilli())/1000)
	EndTimeStr := fmt.Sprintf("%.3f", float64(EndTime.UnixMilli())/1000)
	ResponseBody := QueryResponseBody{}
	err := requests.URL(p.EndPoint+QUERY_API).Param("query", QueryStr).BasicAuth(p.UserName, p.Password).Param("start", StartTimeStr).Param("end", EndTimeStr).Param("step", "60").ToJSON(&ResponseBody).Fetch(context.Background())

	if err != nil {
		log.Println("Failed to query: ", QueryStr)
		log.Println(err.Error())
		return ResponseBody
	} else {
		return ResponseBody
	}
}

func (p *PrometheusServer) GetPodMetricData(Type string, namespaceFilter string, StartTime time.Time, EndTime time.Time) []PromMetricData {
	var QueryStr string
	var promMetricData []PromMetricData

	switch Type {
	case "PodCPUCores":
		QueryStr = POD_CPU_CORES_METRIC_QUERY
	case "PodCPUUsage":
		QueryStr = POD_CPU_USAGE_PERCENTAGE
	case "PodMemory":
		QueryStr = POD_MEMORY_METRIC_QUERY
	case "PodMemoryUsage":
		QueryStr = POD_MEMORY_USAGE_PERCENTAGE_METRIC_QUERY
	case "PodDiskRead":
		QueryStr = POD_DISK_READ_METRIC_QUERY
	case "PodDiskWrite":
		QueryStr = POD_DISK_WRITE_METRIC_QUERY
	case "PodNetworkIn":
		QueryStr = POD_NETWORK_IN_METRIC_QUERY
	case "PodNetworkOut":
		QueryStr = POD_NETWORK_OUT_METRIC_QUERY
	case "PodProcesses":
		QueryStr = POD_PROCESSES_QUERY
	case "NodeCPU":
		QueryStr = NODE_CPU_USAGE_PERCENTAGE_METRIC_QUERY
	case "NodeMemory":
		QueryStr = NODE_MEMORY_USAGE_MB_METRIC_QUERY
	case "NodeMemoryUsage":
		QueryStr = NODE_MEMORY_USAGE_PERCENTAGE_METRIC_QUERY
	case "NodeDiskUsage":
		QueryStr = NODE_DISK_USAGE_PERCENTAGE_METRIC_QUERY
	case "NodeDiskRead":
		QueryStr = NODE_DISK_READ_RATE_METRIC_QUERY
	case "NodeDiskWrite":
		QueryStr = NODE_DISK_WRITE_RATE_METRIC_QUERY
	case "NodeNetworkIn":
		QueryStr = NODE_NETWORK_IN_RATE_METRIC_QUERY
	case "NodeNetworkOut":
		QueryStr = NODE_NETWORK_OUT_RATE_METRIC_QUERY
	case "NodeProcesses":
		QueryStr = NODE_PROCESSES_METRIC_QUERY
	case "NodeBlockedProcesses":
		QueryStr = NODE_BLOCKED_PROCESSES_METRIC_QUERY
	}

	QueryStr = FormatQueryWithNamespaces(QueryStr, namespaceFilter)
	QueryResult := p.Query(QueryStr, StartTime, EndTime)
	for _, Data := range QueryResult.Data.Result {
		NameSpace := Data.Metric.Namespace
		Pod := Data.Metric.Pod

		var Node string = ""
		if Data.Metric.NodeInstance != "" {
			Node = Data.Metric.NodeInstance
		}
		if Data.Metric.Node != "" {
			Node = Data.Metric.Node
		}

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
