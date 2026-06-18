package com.insightfinder.KafkaCollectorAgent.model;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.apache.commons.lang3.StringUtils;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ProjectListKey {

  private static final String COMMA = ",";
  private static final String COLON = ":";
  private static final String EMPTY_STRING = "";
  // The only field whose value is significant for matching (kept value-aware to mirror master).
  private static final String DATASET_ID = "dataset_id";

  // Constraints on the message id fields, keyed by field name. The value is the required value
  // for that field; an empty value means "match any value of this field". Field names are not
  // hard-coded — they come entirely from the projectList configuration.
  private Map<String, String> fieldConstraints;

  public static ProjectListKey parseFromString(String s) {
    Map<String, String> constraints = new LinkedHashMap<>();
    String[] pairs = s.split(COMMA);
    for (String pairStr : pairs) {
      String[] pair = pairStr.split(COLON);
      if (pair.length == 0 || pair.length > 2) {
        return null;
      }
      String field = pair[0].trim();
      if (field.isEmpty()) {
        continue;
      }
      // Mirror master: only dataset_id keeps its value (matched by value). Every other field
      // discards its value, so keys differing only by a non-dataset_id value are equal — matching
      // master, where such fields were stored as a plain boolean.
      String value = EMPTY_STRING;
      if (DATASET_ID.equalsIgnoreCase(field) && pair.length == 2) {
        value = pair[1].trim();
      }
      constraints.put(field, value);
    }
    if (constraints.isEmpty()) {
      return null;
    }
    return new ProjectListKey(constraints);
  }

  public boolean matchedMessageId(KafkaMessageId messageId) {
    if (messageId == null || fieldConstraints == null) {
      return false;
    }
    String idName = messageId.getName();
    if (idName == null) {
      return false;
    }
    // Mirror master's matching semantics:
    // - dataset_id is value-aware: an absent or empty constraint matches any dataset_id value
    //   (master matched on StringUtils.isEmpty(datasetId)), otherwise the value must be equal.
    // - every other field is matched by presence only; its configured value is ignored.
    if (DATASET_ID.equalsIgnoreCase(idName)) {
      String datasetId = fieldConstraints.get(DATASET_ID);
      return StringUtils.isEmpty(datasetId) || datasetId.equals(messageId.getId());
    }
    return fieldConstraints.containsKey(idName);
  }

  /**
   * Whether this key constrains any of the given fields. Used to decide which projects are
   * eligible for metadata broadcast (projects keyed by an excluded field are skipped).
   */
  public boolean referencesAnyField(Collection<String> fields) {
    if (fieldConstraints == null || fields == null) {
      return false;
    }
    for (String field : fields) {
      if (fieldConstraints.containsKey(field)) {
        return true;
      }
    }
    return false;
  }
}
