package com.insightfinder.KafkaCollectorAgent.logic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MetricHeaderEntityTest {
    @Test
    public void test(){
        MetricHeaderEntity metricHeaderEntity = new MetricHeaderEntity("m1", "i1", "g1");
        metricHeaderEntity.setMetric("m2");
        metricHeaderEntity.setInstance("i2");
        metricHeaderEntity.setGroup("g2");
        assert(metricHeaderEntity.getMetric() != null);
        assert(metricHeaderEntity.getGroup() != null);
        assert(metricHeaderEntity.getInstance() != null);
        assert(metricHeaderEntity.generateHeader(true) != null);
        assert(metricHeaderEntity.generateHeader(false) != null);
        assert(metricHeaderEntity.generateHeaderString() != null);
        assert(metricHeaderEntity.equals(metricHeaderEntity));
        assert(!metricHeaderEntity.equals(null));
        MetricHeaderEntity metricHeaderEntity2 = new MetricHeaderEntity("m1", "i1", "g1");
        assert(!metricHeaderEntity.equals(metricHeaderEntity2));
    }

}