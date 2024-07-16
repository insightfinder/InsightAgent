package com.insightfinder.datamodel;

import com.google.gson.annotations.SerializedName;
import java.io.Serializable;
import java.util.Objects;

public class MetricDataPoint implements Serializable {

  @SerializedName(value = "m", alternate = {"metricName"})
  private final String metricName;
  @SerializedName(value = "v", alternate = {"value"})
  private final Float value;

  public MetricDataPoint(String metricName, Float value) {
    this.metricName = metricName;
    this.value = value;
  }

  public String getMetricName() {
    return metricName;
  }

  public Float getValue() {
    return value;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    MetricDataPoint that = (MetricDataPoint) o;
    return Objects.equals(metricName, that.metricName);
  }

  @Override
  public int hashCode() {
    return Objects.hash(metricName);
  }

  @Override
  public String toString() {
    return "MetricDataPoint{" +
        "metricName='" + metricName + '\'' +
        ", value=" + value +
        '}';
  }
}