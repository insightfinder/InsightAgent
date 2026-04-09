package com.insightfinder.KafkaCollectorAgent.logic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.LogProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.logic.logstreaming.LogMessageHandler;
import com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.MetricProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import com.insightfinder.KafkaCollectorAgent.model.ProjectListKey;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessage;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage.LogMetadataMessage;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.lang.reflect.InvocationTargetException;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.reactive.function.client.WebClient;

@ExtendWith(MockitoExtension.class)
class IFStreamingBufferManagerTest {

  IFStreamingBufferManager ifStreamingBufferManager;
  MeterRegistry registry = new SimpleMeterRegistry();
  @Mock
  IFConfig ifConfig;
  @Mock
  IFProjectManager projectManager;
  @Mock
  WebClient webClient;
  @Mock
  MetricProjectConfigParser metricProjectConfigParser;
  @Mock
  LogProjectConfigParser logProjectConfigParser;
  @Mock
  LogMessageHandler logMessageHandler;
  @Mock
  WebClientEndpoints webClientEndpoints;

  @BeforeEach
  void setup() {
    // Provide valid intervals so scheduleAtFixedRate does not throw (period must be > 0).
    // Large values ensure timers never fire during tests.
    when(ifConfig.getBufferingTime()).thenReturn(Integer.MAX_VALUE);
    when(ifConfig.getLogMetadataBufferingTime()).thenReturn(Integer.MAX_VALUE);
    when(ifConfig.getKafkaMetricLogInterval()).thenReturn(Integer.MAX_VALUE);
    ifStreamingBufferManager = new IFStreamingBufferManager(registry, new Gson(), ifConfig,
        projectManager, webClient, metricProjectConfigParser, logProjectConfigParser,
        logMessageHandler, webClientEndpoints);
  }

  @AfterEach
  void tearDown() {
    // Shut down real executor threads so they don't prevent JVM exit after tests.
    // Null checks guard against tests where init() was never called.
    if (ifStreamingBufferManager.getTimerExecutor() != null) {
      ifStreamingBufferManager.getTimerExecutor().shutdownNow();
    }
    if (ifStreamingBufferManager.getWorkerExecutor() != null) {
      ifStreamingBufferManager.getWorkerExecutor().shutdownNow();
    }
  }

  @Nested
  class LogMessageTests {

    @BeforeEach
    void setup() throws InvocationTargetException, NoSuchMethodException, IllegalAccessException {
      when(ifConfig.isLogProject()).thenReturn(true);
      when(ifConfig.getDataFormat()).thenReturn("JSON");
      when(ifConfig.getInstanceList()).thenReturn(new HashSet<>());
      Map<ProjectListKey, ProjectInfo> logProjectList = new HashMap<>();
      logProjectList.put(
          ProjectListKey.builder().datasetId("326CE741-4E1F-404F-BDA2-0D0D48AE4039").hasDatasetName(true).build(),
          ProjectInfo.builder().project("DeviceProcessEvent").system("Lower env Crash").build());
      logProjectList.put(
          ProjectListKey.builder().datasetId("326CE741-4E1F-404F-BDA2-0D0D48AE4039").hasItemId(true).build(),
          ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build());
      logProjectList.put(
          ProjectListKey.builder().datasetId("326CE741-4E1F-404F-BDA2-0D0D48AE4038").hasItemId(true).build(),
          ProjectInfo.builder().project("DeviceProcessEvent2").system("Lower env Crash").build());
      when(ifConfig.getProjectList()).thenReturn("");
      when(logProjectConfigParser.getLogProjectMapping()).thenReturn(logProjectList);
      ifStreamingBufferManager.init();
    }

    @Test
    void testInit() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> expected = new ConcurrentHashMap<>();
      expected.put(
          ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build(),
          ConcurrentHashMap.newKeySet()
      );
      expected.put(
          ProjectInfo.builder().project("DeviceProcessEvent2").system("Lower env Crash").build(),
          ConcurrentHashMap.newKeySet()
      );
      assertThat(ifStreamingBufferManager.getCollectingLogMetadataMap()).isEqualTo(expected);
    }

    @Test
    void testParseLogMetadata() {
      Set<String> metadataTopics = new HashSet<>();
      metadataTopics.add("metadataTopic");
      when(ifConfig.getLogMetadataTopics()).thenReturn(metadataTopics);
      LogMetadataMessage metadataMessage = LogMetadataMessage.builder()
          .outputMessage(new JsonObject())
          .build();
      when(logMessageHandler.processMetadataMessage(anyString())).thenReturn(metadataMessage);
      ifStreamingBufferManager.parseString("metadataTopic", "", 1L);
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> expected = new ConcurrentHashMap<>();
      expected.put(
          ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build(),
          new HashSet<>(Collections.singletonList(new JsonObject())));
      expected.put(
          ProjectInfo.builder().project("DeviceProcessEvent2").system("Lower env Crash").build(),
          new HashSet<>(Collections.singletonList(new JsonObject())));
      assertThat(ifStreamingBufferManager.getCollectingLogMetadataMap()).isEqualTo(expected);
    }

    @Test
    void testSendLogMetadata() {
      ArgumentCaptor<String> messageCapture = ArgumentCaptor.forClass(String.class);
      ArgumentCaptor<String> projectName = ArgumentCaptor.forClass(String.class);
      ArgumentCaptor<String> systemName = ArgumentCaptor.forClass(String.class);
      doNothing().when(webClientEndpoints).sendMetadataToIF(anyString(), anyString(), anyString());
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogMetadataMap = new ConcurrentHashMap<>();
      Set<JsonObject> jsonArray = ConcurrentHashMap.newKeySet();
      jsonArray.add(new JsonObject());
      jsonArray.add(new JsonObject());
      collectingLogMetadataMap.put(
          ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build(),
          jsonArray
      );
      ifStreamingBufferManager.mergeLogMetaDataAndSendToIF(collectingLogMetadataMap);
      verify(webClientEndpoints, times(1)).sendMetadataToIF(messageCapture.capture(), projectName.capture(),
          systemName.capture());
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> expectedCollectingLogMetadataMap = new ConcurrentHashMap<>();
      expectedCollectingLogMetadataMap.put(
          ProjectInfo.builder().project("DeviceProcessEvent1").system("Lower env Crash").build(),
          ConcurrentHashMap.newKeySet()
      );
      assertThat(collectingLogMetadataMap).isEqualTo(expectedCollectingLogMetadataMap);
      assertThat(projectName.getValue()).isEqualTo("DeviceProcessEvent1");
      assertThat(systemName.getValue()).isEqualTo("Lower env Crash");
      assertThat(messageCapture.getValue()).isEqualTo("[{}]");
    }

    @Test
    void testSendLogMetadataMultipleProjects() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogMetadataMap = new ConcurrentHashMap<>();
      Set<JsonObject> jsonArray = ConcurrentHashMap.newKeySet();
      jsonArray.add(new JsonObject());
      collectingLogMetadataMap.put(
          ProjectInfo.builder().project("p").system("s").build(),
          jsonArray
      );
      collectingLogMetadataMap.put(
          ProjectInfo.builder().project("p1").system("s1").build(),
          jsonArray
      );
      ifStreamingBufferManager.mergeLogMetaDataAndSendToIF(collectingLogMetadataMap);
      verify(webClientEndpoints, times(2)).sendMetadataToIF(anyString(), anyString(), anyString());
    }

    @Test
    void testSendLogMetadataEmpty() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogMetadataMap = new ConcurrentHashMap<>();
      ifStreamingBufferManager.mergeLogMetaDataAndSendToIF(collectingLogMetadataMap);
      verify(webClientEndpoints, times(0)).sendMetadataToIF(anyString(), anyString(), anyString());
    }

    @Test
    void testSendLogMetadataInvalidProjectInfo() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogMetadataMap = new ConcurrentHashMap<>();
      Set<JsonObject> jsonArray = ConcurrentHashMap.newKeySet();
      jsonArray.add(new JsonObject());
      collectingLogMetadataMap.put(
          ProjectInfo.builder().system("s").build(),
          jsonArray
      );
      ifStreamingBufferManager.mergeLogMetaDataAndSendToIF(collectingLogMetadataMap);
      verify(webClientEndpoints, times(0)).sendMetadataToIF(anyString(), anyString(), anyString());
    }

    @Test
    void testParseLogData() {
      // Use name("dataset_name") so matchedMessageId hits the hasDatasetName branch,
      // which only matches the one key with hasDatasetName=true → "DeviceProcessEvent".
      // Using name("dataset_id") would match all keys whose datasetId equals the id,
      // making the result non-deterministic over HashMap iteration order.
      LogMessage logMessage = LogMessage.builder()
          .id(LogMessageId.builder().name("dataset_name")
              .id("326CE741-4E1F-404F-BDA2-0D0D48AE4039").build())
          .outputMessage(new JsonObject())
          .build();
      when(logMessageHandler.processLogDataMessage(anyString())).thenReturn(logMessage);
      ifStreamingBufferManager.parseString("logTopic", "", 1L);
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> expected = new ConcurrentHashMap<>();
      expected.put(
          ProjectInfo.builder().project("DeviceProcessEvent").system("Lower env Crash").build(),
          new HashSet<>(Collections.singletonList(new JsonObject())));
      assertThat(ifStreamingBufferManager.getCollectingLogDataMap()).isEqualTo(expected);
    }

    @Test
    void testParseLogDataUnRecognizedId() {
      LogMessage logMessage = LogMessage.builder()
          .id(LogMessageId.builder().name("dataset_id")
              .id("000").build())
          .outputMessage(new JsonObject())
          .build();
      when(logMessageHandler.processLogDataMessage(anyString())).thenReturn(logMessage);
      ifStreamingBufferManager.parseString("logTopic", "", 1L);
      assertThat(ifStreamingBufferManager.getCollectingLogDataMap()).isEmpty();
    }

    @Test
    void testSendLogData() {
      ArgumentCaptor<String> messageCapture = ArgumentCaptor.forClass(String.class);
      ArgumentCaptor<String> projectName = ArgumentCaptor.forClass(String.class);
      ArgumentCaptor<String> systemName = ArgumentCaptor.forClass(String.class);
      doNothing().when(webClientEndpoints).sendDataToIF(anyString(), anyString(), anyString());
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogDataMap = new ConcurrentHashMap<>();
      Set<JsonObject> jsonArray = ConcurrentHashMap.newKeySet();
      jsonArray.add(new JsonObject());
      jsonArray.add(new JsonObject());
      collectingLogDataMap.put(
          ProjectInfo.builder().project("p").system("s").build(),
          jsonArray
      );
      ifStreamingBufferManager.mergeLogDataAndSendToIF(collectingLogDataMap);
      verify(webClientEndpoints, times(1)).sendDataToIF(messageCapture.capture(), projectName.capture(),
          systemName.capture());
      assertThat(collectingLogDataMap).isEmpty();
      assertThat(projectName.getValue()).isEqualTo("p");
      assertThat(systemName.getValue()).isEqualTo("s");
      assertThat(messageCapture.getValue()).isEqualTo("[{}]");
    }

    @Test
    void testSendLogDataMultipleProject() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogDataMap = new ConcurrentHashMap<>();
      Set<JsonObject> jsonArray = ConcurrentHashMap.newKeySet();
      jsonArray.add(new JsonObject());
      collectingLogDataMap.put(
          ProjectInfo.builder().project("p").system("s").build(),
          jsonArray
      );
      collectingLogDataMap.put(
          ProjectInfo.builder().project("p1").system("s1").build(),
          jsonArray
      );
      ifStreamingBufferManager.mergeLogDataAndSendToIF(collectingLogDataMap);
      verify(webClientEndpoints, times(2)).sendDataToIF(anyString(), anyString(), anyString());
    }

    @Test
    void testSendLogDataEmpty() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogDataMap = new ConcurrentHashMap<>();
      ifStreamingBufferManager.mergeLogDataAndSendToIF(collectingLogDataMap);
      verify(webClientEndpoints, times(0)).sendDataToIF(anyString(), anyString(), anyString());
    }

    @Test
    void testSendLogDataInvalidProjectInfo() {
      ConcurrentHashMap<ProjectInfo, Set<JsonObject>> collectingLogDataMap = new ConcurrentHashMap<>();
      Set<JsonObject> jsonArray = ConcurrentHashMap.newKeySet();
      jsonArray.add(new JsonObject());
      collectingLogDataMap.put(
          ProjectInfo.builder().system("s").build(),
          jsonArray
      );
      ifStreamingBufferManager.mergeLogDataAndSendToIF(collectingLogDataMap);
      verify(webClientEndpoints, times(0)).sendDataToIF(anyString(), anyString(), anyString());
    }
  }
}
