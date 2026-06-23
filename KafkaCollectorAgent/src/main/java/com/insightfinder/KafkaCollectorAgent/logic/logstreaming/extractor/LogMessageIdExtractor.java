package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;

/**
 * Strategy for building the log message id used to route a message to a project.
 *
 * <p>This is a separate, vendor-specific seam from {@link LogFieldExtractor}: only vendors that
 * route by a message id (Lenovo) need it. Vendors that read the project directly from the message
 * (Visa) provide an implementation that returns {@code null}. Selected at startup via
 * {@code insight-finder.vendor}.
 */
public interface LogMessageIdExtractor {

  /**
   * Build the log message id from a raw log JSON message.
   *
   * @return the message id, or {@code null} when the vendor does not route by a message id.
   */
  LogMessageId extractMessageId(JsonObject content);
}
