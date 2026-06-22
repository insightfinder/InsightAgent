package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getKeyFromJson;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getTimestampInMillis;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Visa field extraction. Placeholder implementation: instance is read from the configured
 * {@code logInstanceFieldPathList}, and there is no component name yet.
 *
 * <p>TODO: replace with Visa's real rules once they are known (the actual fields and any
 * value/combination logic for instance and component name).
 *
 * <p>Selected when {@code insight-finder.vendor=visa}.
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "visa")
public class VisaLogFieldExtractor implements LogFieldExtractor {

  private final IFConfig ifConfig;

  @Override
  public String extractInstance(JsonObject content) {
    // TODO(visa): confirm the real instance field(s) and any transformation rules.
    return getKeyFromJson(content, ifConfig.getLogInstanceFieldPathList());
  }

  @Override
  public String extractComponentName(JsonObject content) {
    // TODO(visa): implement Visa's component name rule. No component for now.
    return null;
  }

  @Override
  public long extractTimestamp(JsonObject content) {
    // TODO(visa): confirm the real timestamp field(s) and format.
    String timestampStr = getKeyFromJson(content, ifConfig.getLogTimestampFieldPathList());
    if (timestampStr == null) {
      return -1;
    }
    return getTimestampInMillis(timestampStr, ifConfig.getLogTimestampFormat());
  }
}
