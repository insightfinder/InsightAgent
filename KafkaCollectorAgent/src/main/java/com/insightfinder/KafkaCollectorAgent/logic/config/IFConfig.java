package com.insightfinder.KafkaCollectorAgent.logic.config;

import com.google.gson.Gson;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.ArrayList;
import java.util.List;
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
    private String projectKey;
    private String instanceKey;
    private String timestampKey;
    private String metricKey;
    private String valueKey;
    private String projectList;
    private Set<String> instanceList;
    private String metricRegex;
    private String dataFormat;
    private String dataFormatRegex;
    private String agentType;
    private int collectingTime;
    private int bufferSize = 100000;
    private String projectDelimiter;
    private boolean logParsingInfo;
    private boolean logSendingData;
    private String keystoreFile;
    private String keystorePassword;
    private String truststoreFile;
    private String truststorePassword;
    private int bufferingTime;
    private String metricNameFilter;
    private int kafkaMetricLogInterval;
    private boolean fastRecovery;
    private boolean logProject;
    private String logProjectName;
    private String logSystemName;
    private String logTimestampFormat;
    private List<String> logTimestampFieldPathList;
    private List<String> logInstanceFieldPathList;

    private List<String> logComponentFieldPathList;
    private Set<String> logMetadataTopics;

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


    public String getProjectList() {
        return projectList;
    }

    public void setProjectList(String projectList) {
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

    public String getProjectDelimiter() {
        return projectDelimiter;
    }

    public void setProjectDelimiter(String projectDelimiter) {
        this.projectDelimiter = projectDelimiter;
    }

    public boolean isLogParsingInfo() {
        return logParsingInfo;
    }

    public void setLogParsingInfo(boolean logParsingInfo) {
        this.logParsingInfo = logParsingInfo;
    }

    public boolean isLogSendingData() {
        return logSendingData;
    }

    public void setLogSendingData(boolean logSendingData) {
        this.logSendingData = logSendingData;
    }

    public String getKeystoreFile() {
        return keystoreFile;
    }

    public void setKeystoreFile(String keystoreFile) {
        this.keystoreFile = keystoreFile;
    }

    public String getKeystorePassword() {
        return keystorePassword;
    }

    public void setKeystorePassword(String keystorePassword) {
        this.keystorePassword = keystorePassword;
    }

    public String getTruststoreFile() {
        return truststoreFile;
    }

    public void setTruststoreFile(String truststoreFile) {
        this.truststoreFile = truststoreFile;
    }

    public String getTruststorePassword() {
        return truststorePassword;
    }

    public void setTruststorePassword(String truststorePassword) {
        this.truststorePassword = truststorePassword;
    }

    public int getBufferingTime() {
        return bufferingTime;
    }

    public void setBufferingTime(int bufferingTime) {
        this.bufferingTime = bufferingTime;
    }

    public String getMetricNameFilter() {
        return metricNameFilter;
    }

    public void setMetricNameFilter(String metricNameFilter) {
        this.metricNameFilter = metricNameFilter;
    }

    public int getKafkaMetricLogInterval() {
        return kafkaMetricLogInterval;
    }

    public void setKafkaMetricLogInterval(int kafkaMetricLogInterval) {
        this.kafkaMetricLogInterval = kafkaMetricLogInterval;
    }

    public boolean isFastRecovery() {
        return fastRecovery;
    }

    public void setFastRecovery(boolean fastRecovery) {
        this.fastRecovery = fastRecovery;
    }

    public boolean isLogProject() {
        return logProject;
    }

    public void setLogProject(boolean logProject) {
        this.logProject = logProject;
    }

    public String getLogProjectName() {
        return logProjectName;
    }

    public void setLogProjectName(String logProjectName) {
        this.logProjectName = logProjectName;
    }

    public String getLogSystemName() {
        return logSystemName;
    }

    public void setLogSystemName(String logSystemName) {
        this.logSystemName = logSystemName;
    }

    public String getLogTimestampFormat() {
        return logTimestampFormat;
    }

    public void setLogTimestampFormat(String logTimestampFormat) {
        this.logTimestampFormat = logTimestampFormat;
    }

    public List<String> getLogTimestampFieldPathList() {
        return logTimestampFieldPathList;
    }

    public void setLogTimestampFieldPathList(List<String> logTimestampFieldPathList) {
        this.logTimestampFieldPathList = logTimestampFieldPathList;
    }

    public List<String> getLogInstanceFieldPathList() {
        return logInstanceFieldPathList;
    }

    public void setLogInstanceFieldPathList(List<String> logInstanceFieldPathList) {
        this.logInstanceFieldPathList = logInstanceFieldPathList;
    }

    public List<String> getLogComponentFieldPathList() {
        return logComponentFieldPathList;
    }

    public void setLogComponentFieldPathList(List<String> logComponentFieldPathList) {
        this.logComponentFieldPathList = logComponentFieldPathList;
    }

    public Set<String> getLogMetadataTopics() {
        return logMetadataTopics;
    }

    public void setLogMetadataTopics(Set<String> logMetadataTopics) {
        this.logMetadataTopics = logMetadataTopics;
    }
}
