package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming;

import com.google.gson.Gson;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

public class MetricProjectConfigParserTest {

  @Mock
  IFConfig ifConfig;
  MetricProjectConfigParser metricProjectConfigParser;

  @BeforeEach
  void setup() {
    MockitoAnnotations.openMocks(this);
    Gson gson = new Gson();
    metricProjectConfigParser = new MetricProjectConfigParser(ifConfig, gson);
    when(ifConfig.getProjectDelimiter()).thenReturn("\\|");
  }

  @Test
  void testParsingMetricConfigProjectListMapping() {
    when(ifConfig.getProjectList()).thenReturn(
        "{'project_name_123': {'project': 'DeviceProcessEvent','system': 'Lower env Crash'}}");
    Map<String, ProjectInfo> expectedMapping = new HashMap<>();
    expectedMapping.put("project_name_123",
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    assertThat(metricProjectConfigParser.getMetricProjectMapping()).isEqualTo(expectedMapping);
  }

  @Test
  void testParsingMetricConfigProjectListMappingMultipleId() {
    when(ifConfig.getProjectList()).thenReturn(
        "{'project_name_123 | project_name_234 ': {'project': 'DeviceProcessEvent','system': 'Lower env Crash'}}");
    Map<String, ProjectInfo> expectedMapping = new HashMap<>();
    expectedMapping.put("project_name_123",
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    expectedMapping.put("project_name_234",
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    assertThat(metricProjectConfigParser.getMetricProjectMapping()).isEqualTo(expectedMapping);
  }
}
