package main

import (
	"kubernetes-agent/prometheus"
	"time"
)

func main() {
	PrometheusServer := prometheus.Prometheus{
		EndPoint: "http://localhost:9090",
		UserName: "",
		Password: "",
	}
	PrometheusServer.Verify()

	Now := time.Now()
	Before := Now.Add(-time.Minute * 10)
	PrometheusServer.GetMetricData("CPU", Before, Now)
	//MemoryData := PrometheusServer.GetMetricData("Memory", NOW)
	//DiskReadData := PrometheusServer.GetMetricData("DiskRead", NOW)
	//DiskWriteData := PrometheusServer.GetMetricData("DiskWrite", NOW)
	//NetworkInData := PrometheusServer.GetMetricData("DiskWrite", NOW)
	//NetworkOutData := PrometheusServer.GetMetricData("DiskWrite", NOW)

	//for _, data := range DiskReadData {
	//	println(data.NameSpace, data.Pod, data.Time.UnixMilli(), data.Value)
	//}
}
