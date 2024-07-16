package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import java.lang.reflect.Type;
import java.util.HashMap;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class MetricProjectConfigParser {
  public static Type PROJECT_LIST_TYPE = new TypeToken<Map<String, ProjectInfo>>() {
  }.getType();

  @Autowired private final IFConfig ifConfig;
  @Autowired private final Gson gson;


  public Map<String, ProjectInfo> getMetricProjectMapping() {
    Map<String, ProjectInfo> mapping;
    mapping = gson.fromJson(ifConfig.getProjectList(), PROJECT_LIST_TYPE);
    Map<String, ProjectInfo> resultMapping = new HashMap<>();
    for (String projectKey : mapping.keySet()) {
      String[] keys = projectKey.split(ifConfig.getProjectDelimiter());
      for (String key : keys) {
        key = key.trim();
        if (!StringUtils.isEmpty(key)) {
          resultMapping.put(key.trim(), mapping.get(projectKey));
        }
      }
    }
    return resultMapping;
  }
}
