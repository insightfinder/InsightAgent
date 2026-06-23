package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import java.io.IOException;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.util.ResourceUtils;

@ExtendWith(MockitoExtension.class)
class LenovoLogFieldExtractorTest {

  @Mock
  IFConfig ifConfig;

  LenovoLogFieldExtractor extractor;
  JsonObject content;

  @BeforeEach
  void setup() throws IOException {
    extractor = new LenovoLogFieldExtractor(ifConfig);
    String rawMessage = new String(Files.readAllBytes(
        ResourceUtils.getFile("classpath:logMetadataKafkaMessage.json").getAbsoluteFile().toPath()));
    content = new Gson().fromJson(rawMessage, JsonObject.class);
  }

  @Test
  void extractsInstanceFromFirstMatchingPath() {
    when(ifConfig.getLogInstanceFieldPathList())
        .thenReturn(Arrays.asList("missing", "device_id"));
    assertThat(extractor.extractInstance(content)).isEqualTo("device_id");
  }

  @Test
  void extractInstanceReturnsNullWhenNoPathMatches() {
    when(ifConfig.getLogInstanceFieldPathList()).thenReturn(Collections.singletonList("missing"));
    assertThat(extractor.extractInstance(content)).isNull();
  }

  @Test
  void buildsComponentNameFromFirstFullyResolvedGroup() {
    List<List<String>> componentList = new ArrayList<>();
    componentList.add(Arrays.asList("device_info.device_brand", "device_info.device_modeltype"));
    componentList.add(Collections.singletonList("device_info.device_name"));
    when(ifConfig.getLogComponentList()).thenReturn(componentList);
    assertThat(extractor.extractComponentName(content)).isEqualTo("device_brand-device_modeltype");
  }

  @Test
  void fallsBackToNextGroupWhenFirstIncomplete() {
    List<List<String>> componentList = new ArrayList<>();
    // First group has a missing field, so it is skipped; the second group resolves fully.
    componentList.add(Arrays.asList("device_info.device_brand", "device_info.missing"));
    componentList.add(Collections.singletonList("device_info.device_name"));
    when(ifConfig.getLogComponentList()).thenReturn(componentList);
    assertThat(extractor.extractComponentName(content)).isEqualTo("device_name");
  }

  @Test
  void componentNameNullWhenListEmpty() {
    when(ifConfig.getLogComponentList()).thenReturn(Collections.emptyList());
    assertThat(extractor.extractComponentName(content)).isNull();
  }

  @Test
  void extractsFormattedTimestamp() {
    JsonObject json = new JsonObject();
    json.addProperty("ts", "2024-06-30T03:00:16+03:00");
    when(ifConfig.getLogTimestampFieldPathList()).thenReturn(Collections.singletonList("ts"));
    when(ifConfig.getLogTimestampFormat()).thenReturn("yyyy-MM-dd'T'HH:mm:ssZZZZZ");
    assertThat(extractor.extractTimestamp(json)).isEqualTo(1719705616000L);
  }

  @Test
  void extractTimestampReturnsNegativeWhenValueUnparseable() {
    JsonObject json = new JsonObject();
    json.addProperty("ts", "not-a-date");
    when(ifConfig.getLogTimestampFieldPathList()).thenReturn(Collections.singletonList("ts"));
    when(ifConfig.getLogTimestampFormat()).thenReturn("yyyy-MM-dd'T'HH:mm:ssZZZZZ");
    assertThat(extractor.extractTimestamp(json)).isNegative();
  }

  @Test
  void extractTimestampReturnsNegativeWhenFieldMissing() {
    JsonObject json = new JsonObject();
    when(ifConfig.getLogTimestampFieldPathList()).thenReturn(Collections.singletonList("ts"));
    assertThat(extractor.extractTimestamp(json)).isNegative();
  }
}
