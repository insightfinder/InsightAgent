package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import java.util.Collections;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class VisaLogProjectResolverTest {

  @Mock
  IFConfig ifConfig;

  VisaLogProjectResolver resolver;

  @BeforeEach
  void setup() {
    resolver = new VisaLogProjectResolver(ifConfig);
    resolver.init();
  }

  private static LogMessage messageWithData(JsonObject data) {
    JsonObject output = new JsonObject();
    output.add("data", data);
    return LogMessage.builder().outputMessage(output).build();
  }

  @Test
  void readsProjectAndSystemFromMessage() {
    when(ifConfig.getLogProjectFieldPathList()).thenReturn(Collections.singletonList("project"));
    when(ifConfig.getLogSystemFieldPathList()).thenReturn(Collections.singletonList("system"));
    JsonObject data = new JsonObject();
    data.addProperty("project", "VisaProject");
    data.addProperty("system", "VisaSystem");

    assertThat(resolver.resolveProject(messageWithData(data))).isEqualTo(
        ProjectInfo.builder().project("VisaProject").system("VisaSystem").build());
  }

  @Test
  void fallsBackToConfiguredProjectAndSystem() {
    when(ifConfig.getLogProjectFieldPathList()).thenReturn(Collections.singletonList("project"));
    when(ifConfig.getLogSystemFieldPathList()).thenReturn(Collections.singletonList("system"));
    when(ifConfig.getLogProjectName()).thenReturn("DefaultProject");
    when(ifConfig.getLogSystemName()).thenReturn("DefaultSystem");

    assertThat(resolver.resolveProject(messageWithData(new JsonObject()))).isEqualTo(
        ProjectInfo.builder().project("DefaultProject").system("DefaultSystem").build());
  }

  @Test
  void systemFallsBackToProjectWhenAbsent() {
    when(ifConfig.getLogProjectFieldPathList()).thenReturn(Collections.singletonList("project"));
    lenient().when(ifConfig.getLogSystemFieldPathList())
        .thenReturn(Collections.singletonList("system"));
    JsonObject data = new JsonObject();
    data.addProperty("project", "VisaProject");

    assertThat(resolver.resolveProject(messageWithData(data))).isEqualTo(
        ProjectInfo.builder().project("VisaProject").system("VisaProject").build());
  }

  @Test
  void returnsNullWhenNoProjectResolvable() {
    when(ifConfig.getLogProjectFieldPathList()).thenReturn(Collections.singletonList("project"));
    assertThat(resolver.resolveProject(messageWithData(new JsonObject()))).isNull();
  }
}
