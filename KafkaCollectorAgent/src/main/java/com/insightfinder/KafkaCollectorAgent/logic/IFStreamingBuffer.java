package com.insightfinder.KafkaCollectorAgent.logic;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

public class IFStreamingBuffer {
    private Logger logger = Logger.getLogger(IFStreamingBuffer.class.getName());
    private String project;
    private String system;

    private final ConcurrentHashMap<String, InstanceData> allInstanceDataMap;

    public IFStreamingBuffer(String projectName, String systemName) {
        this.project = projectName;
        this.system = systemName;
        this.allInstanceDataMap = new ConcurrentHashMap<>();
    }

    public void addData(String instanceName, long timestamp, String metricName, double value) {
        if (!allInstanceDataMap.containsKey(instanceName)) {
            allInstanceDataMap.put(instanceName, new InstanceData(this.project, instanceName));
        }
        allInstanceDataMap.get(instanceName).addData(metricName, timestamp, value);
    }

    public void clear() {
        this.allInstanceDataMap.clear();
    }

    public IFStreamingBuffer mergeDataAndGetSendingData(IFStreamingBuffer ifStreamingBuffer) {
        IFStreamingBuffer result = new IFStreamingBuffer(ifStreamingBuffer.getProject(), ifStreamingBuffer.getSystem());
        for (String key : allInstanceDataMap.keySet()) {
            InstanceData instanceData = null;
            if (ifStreamingBuffer.allInstanceDataMap.containsKey(key)) {
                instanceData = allInstanceDataMap.get(key).mergeDataAndGetSendingData(ifStreamingBuffer.allInstanceDataMap.remove(key));
            } else {
                instanceData = allInstanceDataMap.remove(key);
            }
            result.allInstanceDataMap.put(key, instanceData);
        }
        return result;
    }

    public Map<String, InstanceData> getAllInstanceDataMap() {
        return allInstanceDataMap;
    }


    public String getProject() {
        return project;
    }

    public void setProject(String project) {
        this.project = project;
    }
    public String getSystem() {
        return system;
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
