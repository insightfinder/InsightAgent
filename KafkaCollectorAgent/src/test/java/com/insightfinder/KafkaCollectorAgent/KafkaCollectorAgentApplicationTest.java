package com.insightfinder.KafkaCollectorAgent;

import org.junit.jupiter.api.Test;
import org.mapdb.DB;
import org.mapdb.DBMaker;

import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ConcurrentMap;

class KafkaCollectorAgentApplicationTest {
    @Test
    public void test(){
        DB db = DBMaker.fileDB("file.db").make();
        ConcurrentMap map = db.hashMap("map").createOrOpen();
        Set<String> stringSet = new HashSet<>();
        stringSet.add("here");
        map.put("something", stringSet);
        if (map.containsKey("something")){
            stringSet = (Set<String>) map.get("something");
            if (stringSet.contains("here")){
                System.out.println("here");
            }
        }
        System.out.println(db.isThreadSafe());
        db.close();
    }

    @Test
    public void test2(){

    }






}