package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Lenovo message id extraction: the id is read from the first field in
 * {@code logMessageIdFieldList} that is present and non-empty, recording both the field name and
 * its value so the resolver can match it against the configured {@code projectList}.
 *
 * <p>Selected when {@code insight-finder.vendor} is {@code lenovo} or unset (the historical
 * default).
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "lenovo", matchIfMissing = true)
public class LenovoLogMessageIdExtractor implements LogMessageIdExtractor {

  private final IFConfig ifConfig;

  @Override
  public LogMessageId extractMessageId(JsonObject content) {
    LogMessageId.LogMessageIdBuilder logMessageIdBuilder = LogMessageId.builder();
    List<String> supportedKeys = ifConfig.getLogMessageIdFieldList();
    if (supportedKeys != null) {
      for (String jsonName : supportedKeys) {
        if (content.has(jsonName) && !StringUtils.isEmpty(content.get(jsonName).getAsString())) {
          return logMessageIdBuilder
              .name(jsonName)
              .id(content.get(jsonName).getAsString())
              .build();
        }
      }
    }
    return logMessageIdBuilder.build();
  }
}
