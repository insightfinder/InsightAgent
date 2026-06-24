package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getKeyFromJson;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getTimestampInMillis;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Visa field extraction.
 *
 * <p>For now {@code extractInstance} and {@code extractComponentName} reuse the Lenovo
 * implementation (inherited unchanged); only the timestamp logic differs, using this branch's
 * latest "format-aware first, then epoch/format-aware" parsing.
 *
 * <p>TODO(visa): once Visa's real instance/component rules are known, override the inherited
 * methods here.
 *
 * <p>Selected when {@code insight-finder.vendor=visa}.
 */
@Component
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "visa")
public class VisaLogFieldExtractor extends LenovoLogFieldExtractor {

  public VisaLogFieldExtractor(IFConfig ifConfig) {
    super(ifConfig);
  }

  @Override
  public long extractTimestamp(JsonObject content) {
    String timestampStr = getKeyFromJson(content, ifConfig.getLogTimestampFieldPathList());
    if (timestampStr == null) {
      return -1;
    }
    return getTimestampInMillis(timestampStr, ifConfig.getLogTimestampFormat(),
        ifConfig.resolvedLogTimestampTimezone());
  }
}

