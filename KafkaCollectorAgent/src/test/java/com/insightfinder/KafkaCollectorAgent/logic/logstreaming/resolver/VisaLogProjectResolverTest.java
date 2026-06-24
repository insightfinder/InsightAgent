package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
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

  @Test
  void usesConfiguredProjectAndSystem() {
    when(ifConfig.getLogProjectName()).thenReturn("VisaProject");
    when(ifConfig.getLogSystemName()).thenReturn("VisaSystem");

    assertThat(resolver.resolveProject(LogMessage.builder().build())).isEqualTo(
        ProjectInfo.builder().project("VisaProject").system("VisaSystem").build());
  }

  @Test
  void returnsNullWhenSystemNameAbsent() {
    when(ifConfig.getLogProjectName()).thenReturn("VisaProject");

    assertThat(resolver.resolveProject(LogMessage.builder().build())).isNull();
  }

  @Test
  void returnsNullWhenProjectNameAbsent() {
    assertThat(resolver.resolveProject(LogMessage.builder().build())).isNull();
  }
}
