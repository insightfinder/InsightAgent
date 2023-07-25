package com.insightfinder.datamodel;

import com.google.gson.annotations.SerializedName;
import java.io.Serializable;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class InstanceData implements Serializable {

  @SerializedName(value = "in", alternate = {"instanceName"})
  private final String instanceName;
  @SerializedName(value = "cn", alternate = {"componentName"})
  private final String componentName;
  @SerializedName(value = "dit", alternate = {"dataInTimestampMap"})
  private TreeMap<Long, DataInTimestamp> dataInTimestampMap;

  public InstanceData(String instanceName, String componentName,
      TreeMap<Long, DataInTimestamp> dataInTimestampMap) {
    this.instanceName = instanceName;
    this.componentName = componentName;
    this.dataInTimestampMap = dataInTimestampMap;
  }

  public InstanceData(String instanceName, String componentName) {
    this.instanceName = instanceName;
    this.componentName = componentName;
    this.dataInTimestampMap = new TreeMap<>();
  }


  public void setDataInTimestampMap(
      TreeMap<Long, DataInTimestamp> dataInTimestampMap) {
    this.dataInTimestampMap = dataInTimestampMap;
  }

  public void addData(String metricName, Long timestamp, Float value) {
    DataInTimestamp dataInTimestamp = dataInTimestampMap.getOrDefault(timestamp,
        new DataInTimestamp(timestamp));
    dataInTimestamp.addData(metricName, value);
    dataInTimestampMap.put(timestamp, dataInTimestamp);
  }

  public String getInstanceName() {
    return instanceName;
  }

  public String getComponentName() {
    return componentName;
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

  @Override
  public String toString() {
    return "InstanceData{" +
        "instanceName='" + instanceName + '\'' +
        ", componentName='" + componentName + '\'' +
        ", dataInTimestampMap=" + dataInTimestampMap +
        '}';
  }
}
