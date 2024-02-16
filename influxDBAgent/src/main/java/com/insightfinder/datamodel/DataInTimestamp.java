package com.insightfinder.datamodel;

import com.google.gson.annotations.SerializedName;
import java.io.Serializable;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class DataInTimestamp implements Serializable {

  @SerializedName(value = "t", alternate = {"timestamp"})
  private Long timestamp;
  private final Set<MetricDataPoint> metricDataPointSet;

  public DataInTimestamp(Long timestamp, Set<MetricDataPoint> metricDataPointSet) {
    this.timestamp = timestamp;
    this.metricDataPointSet = metricDataPointSet;
  }

  public DataInTimestamp(long timestamp) {
    this.timestamp = timestamp;
    this.metricDataPointSet = new HashSet<>();
  }


  public void setTimestamp(long timestamp) {
    this.timestamp = timestamp;
  }

  public long getTimestamp() {
    return timestamp;
  }

  public Set<MetricDataPoint> getMetricDataPointSet() {
    return metricDataPointSet;
  }

  public void addData(String metricName, Float value) {
    metricDataPointSet.add(new MetricDataPoint(metricName, value));
  }


  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    DataInTimestamp that = (DataInTimestamp) o;
    return Objects.equals(timestamp, that.timestamp);
  }

  @Override
  public int hashCode() {
    return Objects.hash(timestamp);
  }

  @Override
  public String toString() {
    return "DataInTimestamp{" +
        "timestamp=" + timestamp +
        ", metricDataPointSet=" + metricDataPointSet +
        '}';
  }
}
