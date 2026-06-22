package com.insightfinder.KafkaCollectorAgent.logic.logstreaming;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor.LogFieldExtractor;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage.LogMetadataMessage;
import java.io.IOException;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Collections;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.util.ResourceUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

public class LogMessageHandlerTest {

  private LogMessageHandler logMessageHandler;
  @Mock
  IFConfig ifConfig;
  @Mock
  LogFieldExtractor logFieldExtractor;
  Gson gson;


  @BeforeEach
  void setup() {
    MockitoAnnotations.openMocks(this);
    gson = new Gson();
    logMessageHandler = new LogMessageHandler(ifConfig, gson, logFieldExtractor);
  }

  private String getExampleMetadataMessage() throws IOException {
    return new String(Files.readAllBytes(
        ResourceUtils.getFile("classpath:logMetadataKafkaMessage.json")
            .getAbsoluteFile()
            .toPath()));
  }

  private String getExampleLogDataMessage() throws IOException {
    return new String(Files.readAllBytes(
        ResourceUtils.getFile("classpath:logDataKafkaMessage.json")
            .getAbsoluteFile()
            .toPath()));
  }

  @Test
  void testProcessLogMetadataMessage() throws IOException {
    String rawMessage = getExampleMetadataMessage();
    when(logFieldExtractor.extractInstance(any())).thenReturn("device_id");
    when(logFieldExtractor.extractComponentName(any()))
        .thenReturn("device_brand-device_modeltype");
    JsonObject outputJson = new JsonObject();
    outputJson.addProperty("instanceName",
        "device_id");
    outputJson.addProperty("componentName", "device_brand-device_modeltype");
    LogMetadataMessage expectedMessage = LogMetadataMessage.builder()
        .outputMessage(outputJson)
        .build();
    assertThat(logMessageHandler.processMetadataMessage(rawMessage)).isEqualTo(expectedMessage);
  }

  @Test
  void testProcessLogDataMessage() throws IOException {
    String rawMessage = getExampleLogDataMessage();
    when(logFieldExtractor.extractTimestamp(any())).thenReturn(1719705616000L);
    when(logFieldExtractor.extractInstance(any())).thenReturn("device_context_id");
    when(ifConfig.getLogMessageIdFieldList())
        .thenReturn(Arrays.asList("dataset_id", "dataset_name", "item_id"));
    JsonObject outputJson = new JsonObject();
    outputJson.addProperty("timestamp", "1719705616000");
    outputJson.addProperty("tag", "device_context_id");
    outputJson.add("data", gson.fromJson(rawMessage, JsonObject.class));
    LogMessage expectedOutput = LogMessage.builder()
        .id(LogMessageId.builder().name("dataset_id").id("dataset_id").build())
        .outputMessage(outputJson)
        .build();
    assertThat(logMessageHandler.processLogDataMessage(rawMessage)).isEqualTo(expectedOutput);
  }
}
