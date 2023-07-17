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

	// CPUData := PrometheusServer.GetMetricData("CPU", Before, Now)
	MemoryData := PrometheusServer.GetMetricData("Memory", Before, Now)
	//DiskReadData := PrometheusServer.GetMetricData("DiskRead", Before, Now)
	//DiskWriteData := PrometheusServer.GetMetricData("DiskWrite", Before, Now)
	//NetworkInData := PrometheusServer.GetMetricData("DiskWrite", Before, Now)
	//NetworkOutData := PrometheusServer.GetMetricData("DiskWrite", Before, Now)

	for _, data := range MemoryData {
		for _, metricData := range data.Data {
			println("NS", data.NameSpace, "Pod", data.Pod, "Container", data.Container, "TS", metricData.TimeStamp, "V", metricData.Value)
			if data.Container == "" {
				println("EMPTY C")
			}
		}
	}
}
