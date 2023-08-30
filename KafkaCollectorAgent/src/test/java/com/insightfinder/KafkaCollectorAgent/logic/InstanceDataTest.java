package com.insightfinder.KafkaCollectorAgent.logic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class InstanceDataTest {
    @Test
    public void test(){
        InstanceData instanceData = new InstanceData("p1", "ins1");
        instanceData.addData("m1", 1693251337000L,1.0);
        assert(instanceData.getInstanceName().equalsIgnoreCase("ins1"));
        assert(instanceData.getProjectName().equalsIgnoreCase("p1"));
        InstanceData instanceData2 = new InstanceData("p1", "ins1");
        instanceData2.addData("m1", 1673251338000L,1.0);
        instanceData2.addData("m1", 1693251337000L,1.0);

        instanceData.mergeDataAndGetSendingData(instanceData2);
        InstanceData instanceData3 = new InstanceData("p1", "ins1");
        instanceData3.addData("m1", 1693251358000L,1.0);
        instanceData.mergeDataAndGetSendingData(instanceData3);
        instanceData.merge(instanceData3);
        assert(instanceData.equals(instanceData));
        assert(instanceData.hashCode() != 0);
        assert(instanceData.equals(instanceData2));
        assert(!instanceData.equals(null));
    }

}