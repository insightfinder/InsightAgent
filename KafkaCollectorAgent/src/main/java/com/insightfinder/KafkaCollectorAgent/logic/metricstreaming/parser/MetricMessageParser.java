package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.parser;

import java.util.List;

/**
 * Strategy for parsing metric kafka messages. This is the vendor-specific seam for metric data:
 * Lenovo and Visa parse different message shapes (and each must handle both JSON and non-JSON
 * payloads). Each vendor provides one implementation, selected at startup via
 * {@code insight-finder.vendor}.
 */
public interface MetricMessageParser {

  /**
   * Build any patterns / project mappings from configuration. Called once at startup, before any
   * message is parsed.
   */
  void init();

  /**
   * Parse a metric message (JSON or otherwise) into zero or more records, each already resolved to
   * its target IF project.
   *
   * @return the parsed records, or an empty list when nothing should be buffered.
   */
  List<MetricRecord> parse(String content);
}
