package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.JsonObject;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;
import java.util.logging.Logger;

public class ThreadBuffer {

    //sort and hash
    public static class ThreadBufferKeySet{
        private Map<String, ThreadBufferKey> map = new HashMap();
        private TreeSet<ThreadBufferKey> keyTreeSet = new TreeSet<>((o1, o2)->{
            if (o1.receiveTime == o2.receiveTime){
                return o1.key.compareTo(o2.key);
            }
            return (int) (o1.receiveTime - o2.receiveTime);
        });

        public ThreadBufferKeySet() {
        }

        public boolean contains(ThreadBufferKey threadBufferKey){
            return map.containsKey(threadBufferKey.key);
        }

        public boolean isEmpty(){
            return map.isEmpty() && keyTreeSet.isEmpty();
        }

        public void add(ThreadBufferKey threadBufferKey){
            if (map.containsKey(threadBufferKey.getKey())){
                if (map.get(threadBufferKey.getKey()).receiveTime > threadBufferKey.getReceiveTime()){
                    keyTreeSet.remove(map.get(threadBufferKey.getKey()));
                    keyTreeSet.add(threadBufferKey);
                    map.put(threadBufferKey.getKey(), threadBufferKey);
                }
            }else {
                map.put(threadBufferKey.getKey(), threadBufferKey);
                keyTreeSet.add(threadBufferKey);
            }
        }

        public ThreadBufferKey first(){
            return keyTreeSet.first();
        }

        public ThreadBufferKey pollFirst(){
            ThreadBufferKey threadBufferKey = keyTreeSet.pollFirst();
            if (map.containsKey(threadBufferKey.key)){
                map.remove(threadBufferKey.key);
            }
            return threadBufferKey;
        }
    }
    public static class ThreadBufferKey{
        public long receiveTime;
        public String key;

        public ThreadBufferKey(long receiveTime, String key) {
            this.receiveTime = receiveTime;
            this.key = key;
        }

        public long getReceiveTime() {
            return receiveTime;
        }

        public void setReceiveTime(long receiveTime) {
            this.receiveTime = receiveTime;
        }

        public String getKey() {
            return key;
        }

        public void setKey(String key) {
            this.key = key;
        }
    }
    private Logger logger = Logger.getLogger(ThreadBuffer.class.getName());
    private ThreadBufferKeySet threadBufferKeySet;
    private  Map<String, Set<IFStreamingBuffer>> buffersMap;

    public ThreadBuffer() {

        threadBufferKeySet = new ThreadBufferKeySet();
        buffersMap = new HashMap<>();
    }

    public void addBuffer(String projectName, String instanceName, String timeStamp, JsonObject jsonObject, long receiveTime){
        synchronized (this){
            String key = String.format("%s-%s-%s", projectName, instanceName, timeStamp);
            ThreadBufferKey threadBufferKey = new ThreadBufferKey(receiveTime, key);
            threadBufferKeySet.add(threadBufferKey);
            if (!buffersMap.containsKey(key)){
                buffersMap.put(key, new HashSet<>());
            }
            buffersMap.get(key).add(new IFStreamingBuffer(projectName, instanceName, timeStamp, jsonObject));
        }
    }

    public void poll(Map<String, Set<IFStreamingBuffer>> collectingDataMap, long timestamp){
        synchronized (this) {
            if (!threadBufferKeySet.isEmpty()){
                while (!threadBufferKeySet.isEmpty()){
                    if (threadBufferKeySet.first().receiveTime <= timestamp){
                        String key = threadBufferKeySet.pollFirst().getKey();
                        if (buffersMap.containsKey(key)){
                            if (!collectingDataMap.containsKey(key)){
                                collectingDataMap.put(key, ConcurrentHashMap.newKeySet());
                            }
                            collectingDataMap.get(key).addAll(buffersMap.remove(key));
                        }
                    }else {
                        break;
                    }
                }
            }
        }
    }

    public Map<String, Set<IFStreamingBuffer>> getBuffersMap() {
        return buffersMap;
    }

    public void setBuffersMap(Map<String, Set<IFStreamingBuffer>> buffersMap) {
        this.buffersMap = buffersMap;
    }
}
