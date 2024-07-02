package com.insightfinder.KafkaCollectorAgent.logic.logstreaming;


import com.google.gson.Gson;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.ProjectListKey;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

public class LogProjectConfigParserTest {

  @Mock
  private IFConfig ifConfig;
  private LogProjectConfigParser logProjectConfigParser;

  @BeforeEach
  void setup() {
    MockitoAnnotations.openMocks(this);
    Gson gson = new Gson();
    logProjectConfigParser = new LogProjectConfigParser(ifConfig, gson);
    when(ifConfig.getProjectDelimiter()).thenReturn("\\|");
  }

  @Test
  public void testParseLogConfigParserWithItemId() {
    when(ifConfig.getProjectList()).thenReturn(
        "{'dataset_id:326CE741-4E1F-404F-BDA2-0D0D48AE4039,item_id': {'project': 'DeviceProcessEvent','system': 'Lower env Crash'}}");
    Map<ProjectListKey, ProjectInfo> expectedMapping = new HashMap<>();
    ProjectListKey key = ProjectListKey.builder()
        .datasetId("326CE741-4E1F-404F-BDA2-0D0D48AE4039")
        .hasItemId(true)
        .hasDatasetName(false)
        .build();
    expectedMapping.put(key,
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    assertThat(logProjectConfigParser.getLogProjectMapping()).isEqualTo(expectedMapping);
  }

  @Test
  public void testParseLogConfigParserWithDatasetName() {
    when(ifConfig.getProjectList()).thenReturn(
        "{'dataset_id:326CE741-4E1F-404F-BDA2-0D0D48AE4039,dataset_name': {'project': 'DeviceProcessEvent','system': 'Lower env Crash'}}");
    Map<ProjectListKey, ProjectInfo> expectedMapping = new HashMap<>();
    ProjectListKey key = ProjectListKey.builder()
        .datasetId("326CE741-4E1F-404F-BDA2-0D0D48AE4039")
        .hasItemId(false)
        .hasDatasetName(true)
        .build();
    expectedMapping.put(key,
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    assertThat(logProjectConfigParser.getLogProjectMapping()).isEqualTo(expectedMapping);
  }

  @Test
  @DisplayName("Test log project list parser for multi dataset_id")
  public void testParseLogConfigParserMultiId() {
    when(ifConfig.getProjectList()).thenReturn(
        "{'dataset_id:E0542A84-B528-44F3-8717-82BF93DFC2FC,item_id | dataset_id:AE8EE408-9F2A-40EF-B2AF-EA0154B67468,dataset_name': {'project': 'DeviceProcessEvent','system': 'Lower env Crash'}}");
    Map<ProjectListKey, ProjectInfo> expectedMapping = new HashMap<>();
    ProjectListKey key1 = ProjectListKey.builder()
        .datasetId("E0542A84-B528-44F3-8717-82BF93DFC2FC")
        .hasItemId(true)
        .build();
    ProjectListKey key2 = ProjectListKey.builder()
        .datasetId("AE8EE408-9F2A-40EF-B2AF-EA0154B67468")
        .hasDatasetName(true)
        .build();
    expectedMapping.put(key1,
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    expectedMapping.put(key2,
        ProjectInfo.builder()
            .project("DeviceProcessEvent")
            .system("Lower env Crash")
            .build());
    assertThat(logProjectConfigParser.getLogProjectMapping()).isEqualTo(expectedMapping);
  }
}
