package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.LogProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.ProjectListKey;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class LenovoLogProjectResolverTest {

  @Mock
  IFConfig ifConfig;
  @Mock
  LogProjectConfigParser logProjectConfigParser;

  LenovoLogProjectResolver resolver;

  private static ProjectListKey key(String... fieldValuePairs) {
    Map<String, String> constraints = new LinkedHashMap<>();
    for (String pair : fieldValuePairs) {
      int colon = pair.indexOf(':');
      if (colon < 0) {
        constraints.put(pair, "");
      } else {
        constraints.put(pair.substring(0, colon), pair.substring(colon + 1));
      }
    }
    return ProjectListKey.builder().fieldConstraints(constraints).build();
  }

  @BeforeEach
  void setup() {
    Map<ProjectListKey, ProjectInfo> logProjectList = new HashMap<>();
    logProjectList.put(
        key("dataset_id:326CE741-4E1F-404F-BDA2-0D0D48AE4039", "dataset_name"),
        ProjectInfo.builder().project("DeviceProcessEvent").system("Lower env Crash").build());
    logProjectList.put(
        key("dataset_id:326CE741-4E1F-404F-BDA2-0D0D48AE4039", "item_id"),
        ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build());
    logProjectList.put(
        key("dataset_id:326CE741-4E1F-404F-BDA2-0D0D48AE4038", "item_id"),
        ProjectInfo.builder().project("DeviceProcessEvent2").system("Lower env Crash").build());
    when(logProjectConfigParser.getLogProjectMapping()).thenReturn(logProjectList);
    when(ifConfig.getLogMetadataExcludeFields()).thenReturn(Collections.singleton("dataset_name"));
    resolver = new LenovoLogProjectResolver(ifConfig, logProjectConfigParser);
    resolver.init();
  }

  @Test
  void resolvesProjectFromMessageId() {
    // name("dataset_name") matches only the key whose fieldConstraints include dataset_name.
    LogMessage logMessage = LogMessage.builder()
        .id(LogMessageId.builder().name("dataset_name")
            .id("326CE741-4E1F-404F-BDA2-0D0D48AE4039").build())
        .outputMessage(new JsonObject())
        .build();
    assertThat(resolver.resolveProject(logMessage)).isEqualTo(
        ProjectInfo.builder().project("DeviceProcessEvent").system("Lower env Crash").build());
  }

  @Test
  void returnsNullForUnrecognizedId() {
    LogMessage logMessage = LogMessage.builder()
        .id(LogMessageId.builder().name("dataset_id").id("000").build())
        .outputMessage(new JsonObject())
        .build();
    assertThat(resolver.resolveProject(logMessage)).isNull();
  }

  @Test
  void metadataProjectsExcludeDatasetNameKeys() {
    assertThat(resolver.getMetadataProjects()).containsExactlyInAnyOrder(
        ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build(),
        ProjectInfo.builder().project("DeviceProcessEvent2").system("Lower env Crash").build());
  }
}
