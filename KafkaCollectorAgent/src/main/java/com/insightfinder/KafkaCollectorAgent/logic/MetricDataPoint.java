package com.insightfinder.KafkaCollectorAgent.logic;

import java.util.Objects;

public class MetricDataPoint {
    private final String metricName;
    private double value;
    private int count;

    public MetricDataPoint(String metricName, double value) {
        this.metricName = metricName;
        this.value = value;
        count = 1;
    }

    public void addData(String metricName, double value) {
        this.value = ((this.value * count) + value) / (count + 1);
        count++;
    }

    public void mergeData(MetricDataPoint metricDataPoint) {
        this.value = ((this.value * count) + metricDataPoint.value * metricDataPoint.count) / (count + metricDataPoint.count);
    }


    public String getMetricName() {
        return metricName;
    }

    public double getValue() {
        return value;
    }


    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (o == null || getClass() != o.getClass()) {
            return false;
        }
        MetricDataPoint that = (MetricDataPoint) o;
        return Objects.equals(metricName, that.metricName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(metricName);
    }
}
