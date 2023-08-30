package com.insightfinder.KafkaCollectorAgent.logic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MetricDataPointTest {
    @Test
    public void test(){
        MetricDataPoint metricDataPoint = new MetricDataPoint("m1", 1);
        assert(metricDataPoint.getMetricName().equalsIgnoreCase("m1"));
        assert(metricDataPoint.getValue() > 0);
        assert(metricDataPoint.equals(metricDataPoint));
        assert(!metricDataPoint.equals(null));
        assert(!metricDataPoint.equals(new MetricDataPoint("m2", 0)));
    }

}