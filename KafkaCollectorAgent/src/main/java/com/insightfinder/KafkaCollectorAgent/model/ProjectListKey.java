package com.insightfinder.KafkaCollectorAgent.model;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_DATASET_ID;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_DATASET_NAME;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_ITEM_ID;

import java.util.HashMap;
import java.util.Map;
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
  // Constraints for configurable id fields other than the three built-in ones.
  // fieldName -> required value (empty means "match any value for this field").
  private Map<String, String> fieldConstraints;

  public static ProjectListKey parseFromString(String s) {
    ProjectListKey projectListKey = new ProjectListKey();
    String[] pairs = s.split(COMMA);
    for (String pairStr : pairs) {
      String[] pair = pairStr.split(COLON);
      if (pair.length == 0 || pair.length > 2) {
        return null;
      }
      String key = pair[0].trim();
      String value = pair.length == 1 ? EMPTY_STRING : pair[1];
      switch (key) {
        case JSON_KEY_DATASET_ID:
          projectListKey.setDatasetId(value);
          break;
        case JSON_KEY_ITEM_ID:
          projectListKey.hasItemId(true);
          break;
        case JSON_KEY_DATASET_NAME:
          projectListKey.hasDatasetName(true);
          break;
        default:
          if (!key.isEmpty()) {
            projectListKey.addFieldConstraint(key, value.trim());
          }
      }
    }
    return projectListKey;
  }

  public void addFieldConstraint(String field, String value) {
    if (fieldConstraints == null) {
      fieldConstraints = new HashMap<>();
    }
    fieldConstraints.put(field, value);
  }

  public boolean matchedMessageId(KafkaMessageId messageId) {
    if (messageId == null) {
      return false;
    }
    String id = messageId.getId();
    String idName = messageId.getName();
    if (idName == null) {
      return false;
    }
    // Built-in id fields keep their original matching semantics.
    if (JSON_KEY_DATASET_ID.equalsIgnoreCase(idName)) {
      // A null datasetId means the key never declared a dataset_id constraint, so it must
      // not match dataset_id messages. An empty (but non-null) datasetId matches any value.
      if (datasetId == null) {
        return false;
      }
      return datasetId.isEmpty() || datasetId.equals(id);
    }
    if (JSON_KEY_DATASET_NAME.equalsIgnoreCase(idName)) {
      return hasDatasetName;
    }
    if (JSON_KEY_ITEM_ID.equalsIgnoreCase(idName)) {
      return hasItemId;
    }
    // Any other configurable id field is matched through fieldConstraints.
    if (fieldConstraints != null && fieldConstraints.containsKey(idName)) {
      String requiredValue = fieldConstraints.get(idName);
      return StringUtils.isEmpty(requiredValue) || requiredValue.equals(id);
    }
    return false;
  }
}
