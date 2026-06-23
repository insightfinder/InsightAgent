package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import com.google.gson.JsonObject;

/**
 * Strategy for extracting the instance and component name from a raw log JSON message.
 *
 * <p>This is a vendor-specific seam in the JSON log pipeline: Lenovo and Visa read these values
 * from different fields and/or combine them with different rules. Each vendor provides one
 * implementation, selected at startup via {@code insight-finder.vendor}.
 */
public interface LogFieldExtractor {

  /**
   * Extract the instance name from a raw log JSON message.
   *
   * @return the instance name, or {@code null} if it cannot be determined.
   */
  String extractInstance(JsonObject content);

  /**
   * Extract the component name from a raw log JSON message.
   *
   * @return the component name, or {@code null} if there is none.
   */
  String extractComponentName(JsonObject content);

  /**
   * Extract the timestamp from a raw log JSON message.
   *
   * @return the timestamp in epoch milliseconds, or a negative value if it cannot be found or
   *     parsed.
   */
  long extractTimestamp(JsonObject content);
}
