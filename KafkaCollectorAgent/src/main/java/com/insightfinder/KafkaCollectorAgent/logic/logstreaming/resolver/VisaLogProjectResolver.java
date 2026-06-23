package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getKeyFromJson;

import com.google.gson.JsonObject;
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
 * Visa project resolution: the project (and optionally the system) is read directly from the JSON
 * log message. The fields to read are configured via {@code logProjectFieldPathList} /
 * {@code logSystemFieldPathList}; when a value is absent from the message, the resolver falls back
 * to the fixed {@code logProjectName} / {@code logSystemName} config, and the system falls back to
 * the project name.
 *
 * <p>Visa has no metadata broadcast flow, so {@link #getMetadataProjects()} returns an empty list.
 *
 * <p>Selected when {@code insight-finder.vendor=visa}.
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "visa")
public class VisaLogProjectResolver implements LogProjectResolver {

  private static final String JSON_NAME_DATA = "data";

  private final IFConfig ifConfig;

  @Override
  public void init() {
    // No mapping to build: project/system are read per-message from the log content.
  }

  @Override
  public ProjectInfo resolveProject(LogMessage logMessage) {
    String project = ifConfig.getLogProjectName();
    String system = ifConfig.getLogSystemName();
    return ProjectInfo.builder().project(project).system(system).build();
  }

  @Override
  public List<ProjectInfo> getMetadataProjects() {
    return Collections.emptyList();
  }

  /**
   * The raw log JSON lives under the {@code data} field of the output message (see
   * {@code LogMessageHandler#processLogDataMessage}); fall back to the output message itself.
   */
  private JsonObject extractData(LogMessage logMessage) {
    if (logMessage == null || logMessage.getOutputMessage() == null) {
      return null;
    }
    JsonObject outputMessage = logMessage.getOutputMessage();
    if (outputMessage.has(JSON_NAME_DATA) && outputMessage.get(JSON_NAME_DATA).isJsonObject()) {
      return outputMessage.getAsJsonObject(JSON_NAME_DATA);
    }
    return outputMessage;
  }
}
