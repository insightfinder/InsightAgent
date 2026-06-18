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
      String value = pair.length == 1 ? EMPTY_STRING : pair[1].trim();
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
    if (idName == null || !fieldConstraints.containsKey(idName)) {
      return false;
    }
    String requiredValue = fieldConstraints.get(idName);
    return StringUtils.isEmpty(requiredValue) || requiredValue.equals(messageId.getId());
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
