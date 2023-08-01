package com.insightfinder.payload;

import com.google.gson.annotations.SerializedName;
import com.insightfinder.datamodel.InstanceData;
import java.util.Map;

public class MetricDataReceivePayload extends BasePayload {

  @SerializedName(value = "i", alternate = {"isTimestampConverted"})
  private final boolean isTimestampConverted = false;
  @SerializedName(value = "idm", alternate = {"instanceDataMap"})
  private final Map<String, InstanceData> instanceDataMap;

  public MetricDataReceivePayload(String projectName, String userName,
      Map<String, InstanceData> instanceDataMap) {
    super(projectName, userName, null);
    this.instanceDataMap = instanceDataMap;
  }

  public boolean isTimestampConverted() {
    return isTimestampConverted;
  }


  public Map<String, InstanceData> getInstanceDataMap() {
    return instanceDataMap;
  }

  @Override
  public String toString() {
    return "MetricDataReceivePayload{" +
        "isTimestampConverted=" + isTimestampConverted +
        ", instanceDataMap=" + instanceDataMap +
        ", projectName='" + projectName + '\'' +
        ", projectType='" + projectType + '\'' +
        ", userName='" + userName + '\'' +
        ", instanceName='" + instanceName + '\'' +
        ", systemName='" + systemName + '\'' +
        '}';
  }
}