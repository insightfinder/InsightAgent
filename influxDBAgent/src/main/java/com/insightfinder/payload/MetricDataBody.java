package com.insightfinder.payload;

public class MetricDataBody {
  private MetricDataReceivePayload data;
  private String licenseKey;
  private String userName;

  public MetricDataBody(MetricDataReceivePayload data, String licenseKey, String userName) {
    this.data = data;
    this.licenseKey = licenseKey;
    this.userName = userName;
  }

  @Override
  public String toString() {
    return "MetricDataBody{" +
        "data=" + data +
        ", licenseKey='" + licenseKey + '\'' +
        ", userName='" + userName + '\'' +
        '}';
  }
}