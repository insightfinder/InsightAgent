package com.insightfinder.KafkaCollectorAgent.logic.logstreaming;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage.LogMetadataMessage;
import java.io.IOException;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.util.ResourceUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

public class LogMessageHandlerTest {

  private LogMessageHandler logMessageHandler;
  @Mock
  IFConfig ifConfig;
  Gson gson;


  @BeforeEach
  void setup() {
    MockitoAnnotations.openMocks(this);
    gson = new Gson();
    logMessageHandler = new LogMessageHandler(ifConfig, gson);
    when(ifConfig.getLogInstanceFieldPathList()).thenReturn(Collections.singletonList("device_id"));
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
    when(ifConfig.getLogInstanceFieldPathList()).thenReturn(Collections.singletonList("device_id"));
    List<List<String>> componentList = new ArrayList<>();
    componentList.add(Arrays.asList("device_info.device_brand", "device_info.device_modeltype"));
    componentList.add(Collections.singletonList("device_info.device_name"));
    when(ifConfig.getLogComponentList()).thenReturn(componentList);
    JsonObject outputJson = new JsonObject();
    outputJson.addProperty("instanceName",
        "0c7cf193e6a6426f2241a671822a5141a9b8b3f7fafc7c8707da0d68981d4466");
    outputJson.addProperty("componentName", "Think-20BTZ0A2US");
    LogMetadataMessage expectedMessage = LogMetadataMessage.builder()
        .outputMessage(outputJson)
        .build();
    assertThat(logMessageHandler.processMetadataMessage(rawMessage)).isEqualTo(expectedMessage);
  }

  @Test
  void testProcessLogDataMessage() throws IOException {
    String rawMessage = getExampleLogDataMessage();
    when(ifConfig.getLogTimestampFieldPathList()).thenReturn(Collections.singletonList("item_time"));
    when(ifConfig.getLogTimestampFormat()).thenReturn("yyyy-MM-dd'T'HH:mm:ssZZZZZ");
    when(ifConfig.getLogInstanceFieldPathList()).thenReturn(Collections.singletonList("device_context_id"));
    JsonObject outputJson = new JsonObject();
    outputJson.addProperty("timestamp", "1719705616000");
    outputJson.addProperty("tag", "CD188F01-506C-4D50-8E7D-5553A87800EE");
    outputJson.add("data", gson.fromJson(rawMessage, JsonObject.class));
    LogMessage expectedOutput = LogMessage.builder()
        .id(LogMessageId.builder().name("dataset_id").id("1118F4A1-5F72-4175-8CCD-36F64DBE5133").build())
        .outputMessage(outputJson)
        .build();
    assertThat(logMessageHandler.processLogDataMessage(rawMessage)).isEqualTo(expectedOutput);
  }
}
