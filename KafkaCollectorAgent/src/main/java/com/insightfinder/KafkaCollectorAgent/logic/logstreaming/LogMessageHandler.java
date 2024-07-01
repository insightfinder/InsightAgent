package com.insightfinder.KafkaCollectorAgent.logic.logstreaming;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_DATASET_ID;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_DATASET_NAME;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.JSON_KEY_ITEM_ID;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getGMTinHourFromMillis;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getKeyFromJson;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage.LogMetadataMessage;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import lombok.RequiredArgsConstructor;
import org.apache.commons.lang3.StringUtils;
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
    String instanceStr = getKeyFromJson(jsonContent, ifConfig.getLogInstanceFieldPathList());
    if (instanceStr == null) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "can not find instance in raw data:" + message);
      }
      return null;
    }
    JsonObject data = new JsonObject();
    data.addProperty(JSON_NAME_INSTANCE_NAME, instanceStr);
    List<List<String>> logComponentList = ifConfig.getLogComponentList();
    if (!logComponentList.isEmpty()) {
      String componentName = getComponentName(jsonContent, logComponentList);
      if (componentName != null) {
        data.addProperty(JSON_NAME_COMPONENT_NAME, componentName);
      }
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
    String timestampStr = getKeyFromJson(jsonContent, ifConfig.getLogTimestampFieldPathList());
    if (timestampStr == null) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "can not find timestamp in raw data: " + jsonContent);
      }
      return null;
    }
    long timestamp = getGMTinHourFromMillis(timestampStr, ifConfig.getLogTimestampFormat());
    if (timestamp < 0) {
      if (ifConfig.isLogParsingInfo()) {
        logger.log(Level.INFO, "can not parse timestamp from raw data: " + jsonContent);
      }
      return null;
    }
    String instanceStr = getKeyFromJson(jsonContent, ifConfig.getLogInstanceFieldPathList());
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
    LogMessageId logMessageId = getLogMessageId(jsonContent);
    return LogMessage.builder()
        .id(logMessageId)
        .outputMessage(data)
        .build();
  }

  private LogMessageId getLogMessageId(JsonObject jsonObject) {
    List<String> supportedKeys = Arrays.asList(JSON_KEY_DATASET_ID, JSON_KEY_DATASET_NAME, JSON_KEY_ITEM_ID);
    LogMessageId.LogMessageIdBuilder logMessageIdBuilder = LogMessageId.builder();
    for (String jsonName: supportedKeys) {
      if (jsonObject.has(jsonName) && !StringUtils.isEmpty(jsonObject.get(jsonName).getAsString())) {
        return logMessageIdBuilder
            .name(jsonName)
            .id(jsonObject.get(jsonName).getAsString())
            .build();
      }
    }
    return logMessageIdBuilder.build();
  }

  private String getComponentName(JsonObject srcData, List<List<String>> logComponentList) {
    String componentName = null;
    if (logComponentList != null) {
      List<String> subComponents = new ArrayList<>();
      for (List<String> componentPaths : logComponentList) {
        componentPaths.forEach(componentPath -> {
          String value = getKeyFromJson(srcData, Collections.singletonList(componentPath));
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
    }
    return componentName;
  }

}
