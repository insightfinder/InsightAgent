package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getGMTinHourFromMillis;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getKeyFromJson;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getTimestampInMillis;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.apache.commons.lang3.StringUtils;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Lenovo field extraction: the instance comes from the first matching path in
 * {@code logInstanceFieldPathList}; the component name is built from {@code logComponentList},
 * where each group of paths is tried in order and the first group whose every path resolves wins,
 * its values joined with {@code "-"}.
 *
 * <p>Selected when {@code insight-finder.vendor} is {@code lenovo} or unset (the historical
 * default).
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "insight-finder.vendor", havingValue = "lenovo", matchIfMissing = true)
public class LenovoLogFieldExtractor implements LogFieldExtractor {

  private final IFConfig ifConfig;

  @Override
  public String extractInstance(JsonObject content) {
    return getKeyFromJson(content, ifConfig.getLogInstanceFieldPathList());
  }

  @Override
  public String extractComponentName(JsonObject content) {
    List<List<String>> logComponentList = ifConfig.getLogComponentList();
    if (logComponentList == null || logComponentList.isEmpty()) {
      return null;
    }
    String componentName = null;
    List<String> subComponents = new ArrayList<>();
    for (List<String> componentPaths : logComponentList) {
      componentPaths.forEach(componentPath -> {
        String value = getKeyFromJson(content, Collections.singletonList(componentPath));
        if (value != null) {
          subComponents.add(value);
        }
      });
      if (subComponents.size() == componentPaths.size()) {
        componentName = String.join("-", subComponents);
        return componentName;
      } else {
        subComponents.clear();
      }
    }
    return componentName;
  }

  @Override
  public long extractTimestamp(JsonObject content) {
    String timestampStr = getKeyFromJson(content, ifConfig.getLogTimestampFieldPathList());
    if (timestampStr == null) {
      return -1;
    }
    // Prefer the original dev-branch conversion; fall back to the epoch/format-aware parser.
    String timestampFormat = ifConfig.getLogTimestampFormat();
    long timestamp = -1;
    if (!StringUtils.isEmpty(timestampFormat)) {
      timestamp = getGMTinHourFromMillis(timestampStr, timestampFormat);
    }
    if (timestamp < 0) {
      timestamp = getTimestampInMillis(timestampStr, timestampFormat);
    }
    return timestamp;
  }
}
