package com.insightfinder.KafkaCollectorAgent.logic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class DataInTimestampTest {
    @Test
    public void test(){
        DataInTimestamp dataInTimestamp = new DataInTimestamp(1692816031000L);
        assert(dataInTimestamp.getTimestamp() == 1692816031000L);
        dataInTimestamp.addData("metric1", 1.0);
        dataInTimestamp.addData("metric2", 2.0);
        dataInTimestamp.addData("metric2", 5.0);

        DataInTimestamp dataInTimestamp2 = new DataInTimestamp(1692816032000L);

        dataInTimestamp2.addData("metric1", 3.0);
        dataInTimestamp2.addData("metric3", 3.0);

        dataInTimestamp.mergeData(dataInTimestamp2);
        assert(!dataInTimestamp.equals(dataInTimestamp2));
        assert(dataInTimestamp.equals(dataInTimestamp));
        assert(!dataInTimestamp.equals(new Object()));
        assert(dataInTimestamp.getMetricDataPointSet() != null);
        assert(dataInTimestamp.hashCode() > 0);
    }

}