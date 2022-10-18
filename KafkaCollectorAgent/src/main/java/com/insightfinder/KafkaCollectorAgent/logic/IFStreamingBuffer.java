package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.JsonObject;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

public class IFStreamingBuffer {
    private Logger logger = Logger.getLogger(IFStreamingBuffer.class.getName());
    private String project;

    private ConcurrentHashMap<String, InstanceData> allInstanceDataMap;

    public IFStreamingBuffer(String projectName) {
        this.project = projectName;
        this.allInstanceDataMap = new ConcurrentHashMap<>();
    }

    public void addData(String instanceName , long timestamp ,String metricName, double value){
        if (!allInstanceDataMap.containsKey(instanceName)){
            allInstanceDataMap.put(instanceName, new InstanceData(instanceName));
        }
        allInstanceDataMap.get(instanceName).addData(metricName, timestamp, value);
    }

    public void clear(){
        this.allInstanceDataMap.clear();
    }

    public IFStreamingBuffer mergeDataAndGetSendingData(IFStreamingBuffer ifStreamingBuffer){
        IFStreamingBuffer result = new IFStreamingBuffer(ifStreamingBuffer.getProject());
        for (String key : allInstanceDataMap.keySet()){
            InstanceData instanceData = null;
            if (ifStreamingBuffer.allInstanceDataMap.containsKey(key)){
                instanceData = allInstanceDataMap.get(key).mergeDataAndGetSendingData(ifStreamingBuffer.allInstanceDataMap.remove(key));
            }else {
                instanceData = allInstanceDataMap.remove(key);
            }
            result.allInstanceDataMap.put(key, instanceData);
        }
        return result;
    }

    public Map<String, InstanceData> getAllInstanceDataMap() {
        return allInstanceDataMap;
    }

    public Logger getLogger() {
        return logger;
    }

    public void setLogger(Logger logger) {
        this.logger = logger;
    }

    public String getProject() {
        return project;
    }

    public void setProject(String project) {
        this.project = project;
    }


    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        IFStreamingBuffer that = (IFStreamingBuffer) o;
        return Objects.equals(logger, that.logger) && Objects.equals(project, that.project);
    }

    @Override
    public int hashCode() {
        return Objects.hash(logger, project);
    }
}
