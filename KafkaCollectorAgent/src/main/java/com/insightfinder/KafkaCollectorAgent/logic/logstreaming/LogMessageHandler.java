package com.insightfinder.KafkaCollectorAgent.logic.logstreaming;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor.LogFieldExtractor;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor.LogMessageIdExtractor;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage.LogMetadataMessage;
import java.util.logging.Level;
import java.util.logging.Logger;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class LogMessageHandler {

  private final Logger logger = Logger.getLogger(LogMessageHandler.class.getName());
  @Autowired
  private final IFConfig ifConfig;
  @Autowired
  private final Gson gson;
  @Autowired
  private final LogFieldExtractor logFieldExtractor;
  // Optional: only vendors that route by a message id (Lenovo) provide a bean; Visa has none.
  @Autowired(required = false)
  private LogMessageIdExtractor logMessageIdExtractor;
  private static final String JSON_NAME_INSTANCE_NAME = "instanceName";
  private static final String JSON_NAME_COMPONENT_NAME = "componentName";
  private static final String JSON_NAME_TIMESTAMP = "timestamp";
  private static final String JSON_NAME_TAG = "tag";
  private static final String JSON_NAME_DATA = "data";

  /**
   * Generate output from log metadata kafka message
   */
  public LogMetadataMessage processMetadataMessage(String message) {
    JsonObject jsonContent = gson.fromJson(message, JsonObject.class);
    String instanceStr = logFieldExtractor.extractInstance(jsonContent);
    if (instanceStr == null) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "can not find instance in raw data:" + message);
      }
      return null;
    }
    JsonObject data = new JsonObject();
    data.addProperty(JSON_NAME_INSTANCE_NAME, instanceStr);
    String componentName = logFieldExtractor.extractComponentName(jsonContent);
    if (componentName != null) {
      data.addProperty(JSON_NAME_COMPONENT_NAME, componentName);
    }
    return LogMetadataMessage.builder()
        .outputMessage(data)
        .build();
  }

  /**
   * Generate output from log kafka message
   */
  public LogMessage processLogDataMessage(String message) {
    JsonObject jsonContent = gson.fromJson(message, JsonObject.class);
    long timestamp = logFieldExtractor.extractTimestamp(jsonContent);
    if (timestamp < 0) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "can not parse timestamp from raw data: " + jsonContent);
      }
      return null;
    }
    String instanceStr = logFieldExtractor.extractInstance(jsonContent);
    if (instanceStr == null) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "can not find instance in raw data:" + jsonContent);
      }
      return null;
    }
    JsonObject data = new JsonObject();
    data.addProperty(JSON_NAME_TIMESTAMP, Long.toString(timestamp));
    data.addProperty(JSON_NAME_TAG, instanceStr);
    data.add(JSON_NAME_DATA, jsonContent);
    LogMessageId logMessageId =
        logMessageIdExtractor == null ? null : logMessageIdExtractor.extractMessageId(jsonContent);
    return LogMessage.builder()
        .id(logMessageId)
        .outputMessage(data)
        .build();
  }

}
