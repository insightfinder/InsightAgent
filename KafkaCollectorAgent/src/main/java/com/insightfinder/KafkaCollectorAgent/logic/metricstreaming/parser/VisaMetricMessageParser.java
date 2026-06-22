package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.parser;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import java.util.Collections;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Visa metric parsing. Placeholder implementation: returns no records for both JSON and non-JSON
 * messages.
 *
 * <p>TODO(visa): implement Visa's metric parsing once the message shape is known (project /
 * instance / timestamp / metric / value extraction for both JSON and non-JSON payloads).
 *
 * <p>Selected when {@code insight-finder.vendor=visa}.
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "visa")
public class VisaMetricMessageParser implements MetricMessageParser {

  private final IFConfig ifConfig;

  @Override
  public void init() {
    // TODO(visa): build any patterns / project mappings from configuration.
  }

  @Override
  public List<MetricRecord> parse(String content) {
    // TODO(visa): parse Visa metric messages (JSON and non-JSON) into records.
    return Collections.emptyList();
  }
}
