package db

import "time"

type InstanceContainerPair struct {
	Instance  string
	Container string
}

type MetricNameValuePair struct {
	Timestamp   time.Time
	MetricName  string
	MetricValue float64
}
