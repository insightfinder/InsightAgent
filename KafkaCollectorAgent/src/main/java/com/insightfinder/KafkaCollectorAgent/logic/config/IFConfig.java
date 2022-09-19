package com.insightfinder.KafkaCollectorAgent.logic.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.Set;

@Configuration
@ConfigurationProperties(prefix = "insight-finder")
public class IFConfig {
    private String userName;
    private String serverUrl;
    private String serverUri;
    private String checkAndCreateUri;
    private String licenseKey;
    private int samplingIntervalInSeconds;
    private String systemName;
    private String projectKey;
    private String instanceKey;
    private String timestampKey;
    private String metricKey;
    private String valueKey;
    private Set<String> projectList;
    private Set<String>instanceList;
    private String  metricRegex;
    private String dataFormat;
    private String dataFormatRegex;
    private String  agentType;
    private int  collectingTime;
    private int  bufferSize=100000;

    public String getUserName() {
        return userName;
    }

    public void setUserName(String userName) {
        this.userName = userName;
    }

    public String getServerUrl() {
        return serverUrl;
    }

    public void setServerUrl(String serverUrl) {
        this.serverUrl = serverUrl;
    }

    public String getServerUri() {
        return serverUri;
    }

    public void setServerUri(String serverUri) {
        this.serverUri = serverUri;
    }

    public String getCheckAndCreateUri() {
        return checkAndCreateUri;
    }

    public void setCheckAndCreateUri(String checkAndCreateUri) {
        this.checkAndCreateUri = checkAndCreateUri;
    }

    public String getLicenseKey() {
        return licenseKey;
    }

    public void setLicenseKey(String licenseKey) {
        this.licenseKey = licenseKey;
    }

    public int getSamplingIntervalInSeconds() {
        return samplingIntervalInSeconds;
    }

    public void setSamplingIntervalInSeconds(int samplingIntervalInSeconds) {
        this.samplingIntervalInSeconds = samplingIntervalInSeconds;
    }

    public String getSystemName() {
        return systemName;
    }

    public void setSystemName(String systemName) {
        this.systemName = systemName;
    }

    public String getInstanceKey() {
        return instanceKey;
    }

    public void setInstanceKey(String instanceKey) {
        this.instanceKey = instanceKey;
    }

    public String getTimestampKey() {
        return timestampKey;
    }

    public void setTimestampKey(String timestampKey) {
        this.timestampKey = timestampKey;
    }

    public Set<String> getProjectList() {
        return projectList;
    }

    public void setProjectList(Set<String> projectList) {
        this.projectList = projectList;
    }
    public Set<String> getInstanceList() {
        return instanceList;
    }

    public void setInstanceList(Set<String> instanceList) {
        this.instanceList = instanceList;
    }

    public String getMetricRegex() {
        return metricRegex;
    }

    public void setMetricRegex(String metricRegex) {
        this.metricRegex = metricRegex;
    }

    public String getAgentType() {
        return agentType;
    }

    public void setAgentType(String agentType) {
        this.agentType = agentType;
    }

    public int getCollectingTime() {
        return collectingTime;
    }

    public void setCollectingTime(int collectingTime) {
        this.collectingTime = collectingTime;
    }

    public int getBufferSize() {
        return bufferSize;
    }

    public void setBufferSize(int bufferSize) {
        this.bufferSize = bufferSize;
    }

    public String getDataFormat() {
        return dataFormat;
    }

    public void setDataFormat(String dataFormat) {
        this.dataFormat = dataFormat;
    }

    public String getDataFormatRegex() {
        return dataFormatRegex;
    }

    public void setDataFormatRegex(String dataFormatRegex) {
        this.dataFormatRegex = dataFormatRegex;
    }

    public String getProjectKey() {
        return projectKey;
    }

    public void setProjectKey(String projectKey) {
        this.projectKey = projectKey;
    }

    public String getMetricKey() {
        return metricKey;
    }

    public void setMetricKey(String metricKey) {
        this.metricKey = metricKey;
    }

    public String getValueKey() {
        return valueKey;
    }

    public void setValueKey(String valueKey) {
        this.valueKey = valueKey;
    }
}
