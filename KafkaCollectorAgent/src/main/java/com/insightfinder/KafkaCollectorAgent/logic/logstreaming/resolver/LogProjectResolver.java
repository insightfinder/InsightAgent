package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.resolver;

import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import java.util.List;

/**
 * Strategy for routing a parsed log message to its target InsightFinder project.
 *
 * <p>This is the main vendor-specific seam in the JSON log pipeline. Lenovo derives the project
 * from a log message id (dataset_id / dataset_name / item_id) looked up against the configured
 * {@code projectList}; Visa reads the project directly from the message. Each vendor provides one
 * implementation, selected at startup via {@code insight-finder.vendor}.
 */
public interface LogProjectResolver {

  /**
   * Build any internal project mappings from configuration. Called once at startup, before any
   * message is routed.
   */
  void init();

  /**
   * Route a parsed log message to its target IF project.
   *
   * @return the matched project, or {@code null} if the message does not belong to any project.
   */
  ProjectInfo resolveProject(LogMessage logMessage);

  /**
   * Projects that should receive broadcast log metadata. Returns an empty list when the vendor has
   * no metadata broadcast flow.
   */
  List<ProjectInfo> getMetadataProjects();
}
