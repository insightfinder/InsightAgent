package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.parser;

import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;

/**
 * A single parsed metric data point, already resolved to its target IF project. Produced by a
 * {@link MetricMessageParser} and buffered by the streaming buffer manager.
 */
@Data
@Builder
@AllArgsConstructor
public class MetricRecord {
  private ProjectInfo projectInfo;
  private String instanceName;
  private long timestamp;
  private String metricName;
  private double value;
}
