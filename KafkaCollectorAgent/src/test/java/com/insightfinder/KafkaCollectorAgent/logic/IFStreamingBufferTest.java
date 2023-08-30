package com.insightfinder.KafkaCollectorAgent.logic;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class IFStreamingBufferTest {
    @Test
    public void test(){
        IFStreamingBuffer ifStreamingBuffer = new IFStreamingBuffer("p1", "s1");
        ifStreamingBuffer.addData("i1", 10000L, "m1", 1.0);
        ifStreamingBuffer.addData("i1", 10000L, "m2", 1.0);
        ifStreamingBuffer.addData("i1", 10001L, "m2", 1.0);

        IFStreamingBuffer ifStreamingBuffer2 = new IFStreamingBuffer("p1", "s1");
        ifStreamingBuffer2.addData("i1", 10000L, "m1", 1.0);
        ifStreamingBuffer2.addData("i2", 10003L, "m2", 1.0);
        ifStreamingBuffer2.addData("i6", 10001L, "m2", 1.0);
        ifStreamingBuffer.mergeDataAndGetSendingData(ifStreamingBuffer2);
        assert(ifStreamingBuffer.equals(ifStreamingBuffer));
        assert(!ifStreamingBuffer.equals(null));
        assert(ifStreamingBuffer.equals(ifStreamingBuffer2));
        IFStreamingBuffer ifStreamingBuffer3 = new IFStreamingBuffer("p2", "s2");
        assert(!ifStreamingBuffer.equals(ifStreamingBuffer3));
        ifStreamingBuffer3.clear();
        assert(ifStreamingBuffer.getAllInstanceDataMap() != null);
        ifStreamingBuffer3.setProject("p3");
        assert(ifStreamingBuffer3.getProject().equalsIgnoreCase("p3"));
        assert(ifStreamingBuffer.hashCode() != 0);
    }
}