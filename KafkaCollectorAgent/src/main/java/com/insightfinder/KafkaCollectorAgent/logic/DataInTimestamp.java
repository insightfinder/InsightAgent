package com.insightfinder.KafkaCollectorAgent.logic;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class DataInTimestamp {
    private final long timestamp;
    private final ConcurrentHashMap<String ,MetricDataPoint> metricDataPointMap;

    public DataInTimestamp(long timestamp) {
        this.timestamp = timestamp;
        this.metricDataPointMap = new ConcurrentHashMap<>();
    }

    public long getTimestamp() {
        return timestamp;
    }

    public Set<MetricDataPoint> getMetricDataPointSet() {
        return new HashSet<>(metricDataPointMap.values());
    }

    public void addData(String metricName, double value) {
        if (!metricDataPointMap.containsKey(metricName)){
            metricDataPointMap.put(metricName, new MetricDataPoint(metricName, value));
        }else {
            metricDataPointMap.get(metricName).addData(metricName, value);
        }
    }

    public void mergeData(DataInTimestamp dataInTimestamp) {
        for (String key : dataInTimestamp.metricDataPointMap.keySet()){
            if (!metricDataPointMap.containsKey(key)){
                metricDataPointMap.put(key, dataInTimestamp.metricDataPointMap.get(key));
            }else {
                metricDataPointMap.get(key).mergeData(dataInTimestamp.metricDataPointMap.get(key));
            }
        }


    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (o == null || getClass() != o.getClass()) {
            return false;
        }
        DataInTimestamp that = (DataInTimestamp) o;
        return timestamp == that.timestamp;
    }

    @Override
    public int hashCode() {
        return Objects.hash(timestamp);
    }
}
