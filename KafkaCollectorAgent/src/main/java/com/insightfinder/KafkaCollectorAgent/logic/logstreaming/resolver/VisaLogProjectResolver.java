package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import java.util.Collections;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Visa project resolution: every Visa log message is routed to a single, fixed project / system
 * taken from configuration ({@code logProjectName} / {@code logSystemName}). The project and system
 * are never derived from the message content. When no system is configured, it falls back to the
 * project name.
 *
 * <p>Visa has no metadata broadcast flow, so {@link #getMetadataProjects()} returns an empty list.
 *
 * <p>Selected when {@code insight-finder.vendor=visa}.
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "visa")
public class VisaLogProjectResolver implements LogProjectResolver {

  private final IFConfig ifConfig;

  @Override
  public void init() {
    // No mapping to build: the target project/system come from fixed config.
  }

  @Override
  public ProjectInfo resolveProject(LogMessage logMessage) {
    String project = ifConfig.getLogProjectName();
    if (StringUtils.isEmpty(project)) {
      return null;
    }
    String system = ifConfig.getLogSystemName();
    if (StringUtils.isEmpty(system)) {
      return null;
    }
    return ProjectInfo.builder().project(project).system(system).build();
  }

  @Override
  public List<ProjectInfo> getMetadataProjects() {
    return Collections.emptyList();
  }
}
