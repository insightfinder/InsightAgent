package com.insightfinder.KafkaCollectorAgent.logic.config;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import javax.annotation.PostConstruct;
import lombok.Data;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration
@ConfigurationProperties(prefix = "insight-finder")
@PropertySource("/config.properties")
@Data
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
  private String projectDelimiter;
  private boolean logParsingInfo;
  private boolean logSendingData;
  private String keystoreFile;
  private String keystorePassword;
  private String truststoreFile;
  private String truststorePassword;
  private int bufferingTime;
  private int logMetadataBufferingTime;
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
  private List<List<String>> logComponentList;

  @PostConstruct
  public void init() {
    logComponentList = parseLogComponentList();
  }

  private List<List<String>> parseLogComponentList() {
    List<String> logComponentFieldPathList = getLogComponentFieldPathList();
    List<List<String>> ans = new ArrayList<>();
    if (logComponentFieldPathList != null) {
      logComponentFieldPathList.forEach(pathStr -> {
        List<String> pathList = Arrays.asList(pathStr.split("&"));
        if (!pathList.isEmpty()) {
          ans.add(pathList);
        }
      });
    }
    return ans;
  }
}
