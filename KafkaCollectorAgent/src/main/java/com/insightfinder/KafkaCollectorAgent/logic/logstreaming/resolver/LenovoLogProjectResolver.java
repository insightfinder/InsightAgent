package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.LogProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.model.KafkaMessageId;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.ProjectListKey;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Map.Entry;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Lenovo project resolution: a log message carries an id (dataset_id / dataset_name / item_id),
 * which is matched against the configured {@code projectList} to find the target project. Metadata
 * is broadcast to every project whose key does not reference an excluded field.
 *
 * <p>Selected when {@code insight-finder.vendor} is {@code lenovo} or unset (the historical
 * default), so existing deployments keep working unchanged.
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "lenovo", matchIfMissing = true)
public class LenovoLogProjectResolver implements LogProjectResolver {

  private final IFConfig ifConfig;
  private final LogProjectConfigParser logProjectConfigParser;

  private Map<ProjectListKey, ProjectInfo> logProjectList;
  private List<ProjectInfo> logMetadataProjectList = new ArrayList<>();

  @Override
  public void init() {
    logProjectList = logProjectConfigParser.getLogProjectMapping();
    Set<String> metadataExcludeFields = ifConfig.getLogMetadataExcludeFields();
    logMetadataProjectList = logProjectList.entrySet().stream()
        .filter(entry -> !entry.getKey().referencesAnyField(metadataExcludeFields))
        .map(Entry::getValue)
        .collect(Collectors.toList());
  }

  @Override
  public ProjectInfo resolveProject(LogMessage logMessage) {
    if (logMessage == null || logProjectList == null) {
      return null;
    }
    return getIFProjectInfoFromLogMessageId(logMessage.getId());
  }

  @Override
  public List<ProjectInfo> getMetadataProjects() {
    return logMetadataProjectList;
  }

  private ProjectInfo getIFProjectInfoFromLogMessageId(KafkaMessageId messageId) {
    for (ProjectListKey projectListKey : logProjectList.keySet()) {
      if (projectListKey.matchedMessageId(messageId)) {
        return logProjectList.get(projectListKey);
      }
    }
    return null;
  }
}
