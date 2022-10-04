package com.insightfinder.KafkaCollectorAgent;

import com.insightfinder.KafkaCollectorAgent.logic.ThreadBuffer;
import org.junit.jupiter.api.Test;

import java.util.TreeMap;

import static org.junit.jupiter.api.Assertions.*;

class KafkaCollectorAgentApplicationTest {
    @Test
    public void test(){
        ThreadBuffer.ThreadBufferKeySet threadBufferKeySet = new ThreadBuffer.ThreadBufferKeySet();
        ThreadBuffer.ThreadBufferKey threadBuffer0 = new ThreadBuffer.ThreadBufferKey(10, "threadBuffer1");

        ThreadBuffer.ThreadBufferKey threadBuffer1 = new ThreadBuffer.ThreadBufferKey(100, "threadBuffer");
        ThreadBuffer.ThreadBufferKey threadBuffer2 = new ThreadBuffer.ThreadBufferKey(101, "threadBuffer");
        ThreadBuffer.ThreadBufferKey threadBuffer3 = new ThreadBuffer.ThreadBufferKey(8, "threadBuffer");
        threadBufferKeySet.add(threadBuffer0);
        threadBufferKeySet.add(threadBuffer1);
        threadBufferKeySet.add(threadBuffer2);
        threadBufferKeySet.add(threadBuffer3);
//        System.out.println(keyTreeMap.firstKey().getReceiveTime());

        System.out.println(threadBufferKeySet.first().getReceiveTime());
    }
}