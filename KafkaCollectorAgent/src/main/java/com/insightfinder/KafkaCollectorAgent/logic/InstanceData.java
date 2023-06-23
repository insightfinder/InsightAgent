package com.insightfinder.KafkaCollectorAgent.logic;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public class InstanceData {
    private final String projectName;
    private final String instanceName;
    private final ConcurrentHashMap<Long, DataInTimestamp> dataInTimestampMap;

    public InstanceData(String projectName, String instanceName) {
        this.projectName = projectName;
        this.instanceName = instanceName;
        this.dataInTimestampMap = new ConcurrentHashMap<>();
    }

    public void addData(String metricName, long timestamp, double value) {
        timestamp -= timestamp % (60000L);
        DataInTimestamp dataInTimestamp = dataInTimestampMap.getOrDefault(timestamp, new DataInTimestamp(timestamp));
        dataInTimestamp.addData(metricName, value);
        dataInTimestampMap.put(timestamp, dataInTimestamp);
    }

    public String getProjectName() {
        return projectName;
    }

    public String getInstanceName() {
        return instanceName;
    }

    public InstanceData mergeDataAndGetSendingData(InstanceData instanceData) {
        InstanceData result = new InstanceData(instanceData.getProjectName(), instanceData.getInstanceName());
        for (Long key : dataInTimestampMap.keySet()) {
            if (!instanceData.dataInTimestampMap.containsKey(key)) {
                result.dataInTimestampMap.put(key, dataInTimestampMap.remove(key));
            }
        }

        for (Long key : instanceData.dataInTimestampMap.keySet()) {
            if (dataInTimestampMap.containsKey(key)) {
                dataInTimestampMap.get(key).mergeData(instanceData.dataInTimestampMap.remove(key));
            } else {
                dataInTimestampMap.put(key, instanceData.dataInTimestampMap.remove(key));
            }
        }
        instanceData.dataInTimestampMap.clear();
        return result;
    }


    public Map<Long, DataInTimestamp> getDataInTimestampMap() {
        return dataInTimestampMap;
    }

    public void merge(InstanceData other) {
        if (this.equals(other) && other.getDataInTimestampMap() != null) {
            this.dataInTimestampMap.putAll(other.getDataInTimestampMap());
        }
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (o == null || getClass() != o.getClass()) {
            return false;
        }
        InstanceData that = (InstanceData) o;
        return Objects.equals(instanceName, that.instanceName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(instanceName);
    }
}
