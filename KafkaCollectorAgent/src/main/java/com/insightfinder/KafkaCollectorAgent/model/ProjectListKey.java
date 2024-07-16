package com.insightfinder.KafkaCollectorAgent.model;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_DATASET_ID;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_DATASET_NAME;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_ITEM_ID;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import lombok.experimental.Accessors;
import org.apache.commons.lang3.StringUtils;

@Data
@RequiredArgsConstructor
@AllArgsConstructor
@Builder
public class ProjectListKey {

  private static final String COMMA = ",";
  private static final String COLON = ":";
  private static final String EMPTY_STRING = "";

  private String datasetId;
  @Accessors(fluent = true)
  private boolean hasDatasetName;
  @Accessors(fluent = true)
  private boolean hasItemId;

  public static ProjectListKey parseFromString(String s) {
    ProjectListKey projectListKey = new ProjectListKey();
    String[] pairs = s.split(COMMA);
    for (String pairStr : pairs) {
      String[] pair = pairStr.split(COLON);
      if (pair.length == 0 || pair.length > 2) {
        return null;
      }
      String key = pair[0].trim();
      switch (key) {
        case JSON_KEY_DATASET_ID:
          String value = pair.length == 1 ? EMPTY_STRING : pair[1];
          projectListKey.setDatasetId(value);
          break;
        case JSON_KEY_ITEM_ID:
          projectListKey.hasItemId(true);
          break;
        case JSON_KEY_DATASET_NAME:
          projectListKey.hasDatasetName(true);
      }
    }
    return projectListKey;
  }

  public boolean matchedMessageId(KafkaMessageId messageId) {
    if (messageId == null) {
      return false;
    }
    String id = messageId.getId();
    String idName = messageId.getName();
    if (JSON_KEY_DATASET_ID.equalsIgnoreCase(idName)) {
      return StringUtils.isEmpty(datasetId) || datasetId.equals(id);
    } else {
      return (JSON_KEY_DATASET_NAME.equalsIgnoreCase(idName) && hasDatasetName)
          || (JSON_KEY_ITEM_ID.equalsIgnoreCase(idName) && hasItemId);
    }
  }
}
