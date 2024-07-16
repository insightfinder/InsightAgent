package com.insightfinder.KafkaCollectorAgent.logic.logstreaming;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.ProjectListKey;
import java.lang.reflect.Type;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class LogProjectConfigParser {

  public static Type PROJECT_LIST_TYPE = new TypeToken<Map<String, ProjectInfo>>() {
  }.getType();

  @Autowired
  private final IFConfig ifConfig;
  @Autowired
  private final Gson gson;

  public LogProjectConfigParser(IFConfig ifConfig, Gson gson) {
    this.ifConfig = ifConfig;
    this.gson = gson;
  }

  public Map<ProjectListKey, ProjectInfo> getLogProjectMapping() {
    Map<String, ProjectInfo> mapping;
    mapping = gson.fromJson(ifConfig.getProjectList(), PROJECT_LIST_TYPE);
    Map<ProjectListKey, ProjectInfo> resultMapping = new HashMap<>();
    for (String projectKey : mapping.keySet()) {
      String[] keys = projectKey.split(ifConfig.getProjectDelimiter());
      for (String key : keys) {
        ProjectListKey projectListKey = ProjectListKey.parseFromString(key);
        if (projectListKey != null) {
          resultMapping.put(ProjectListKey.parseFromString(key), mapping.get(projectKey));
        }
      }
    }
    return resultMapping;
  }

  public Map<ProjectListKey, ProjectInfo> getLogMetadataProjectMapping() {
    Map<String, ProjectInfo> mapping;
    mapping = gson.fromJson(ifConfig.getProjectList(), PROJECT_LIST_TYPE);
    Map<ProjectListKey, ProjectInfo> resultMapping = new HashMap<>();
    for (String projectKey : mapping.keySet()) {
      String[] keys = projectKey.split(ifConfig.getProjectDelimiter());
      for (String key : keys) {
        ProjectListKey projectListKey = ProjectListKey.parseFromString(key);
        if (projectListKey != null) {
          if (!projectListKey.hasDatasetName()) {
            resultMapping.put(projectListKey, mapping.get(projectKey));
          }
        }
      }
    }
    return resultMapping;
  }
}
