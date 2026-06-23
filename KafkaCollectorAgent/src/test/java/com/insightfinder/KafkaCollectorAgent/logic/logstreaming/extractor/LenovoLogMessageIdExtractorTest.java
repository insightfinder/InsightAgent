package com.insightfinder.KafkaCollectorAgent.logic.logstreaming.extractor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import java.io.IOException;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Collections;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.util.ResourceUtils;

@ExtendWith(MockitoExtension.class)
class LenovoLogMessageIdExtractorTest {

  @Mock
  IFConfig ifConfig;

  LenovoLogMessageIdExtractor extractor;
  JsonObject content;

  @BeforeEach
  void setup() throws IOException {
    extractor = new LenovoLogMessageIdExtractor(ifConfig);
    String rawMessage = new String(Files.readAllBytes(
        ResourceUtils.getFile("classpath:logMetadataKafkaMessage.json").getAbsoluteFile().toPath()));
    content = new Gson().fromJson(rawMessage, JsonObject.class);
  }

  @Test
  void extractsMessageIdFromFirstMatchingField() {
    when(ifConfig.getLogMessageIdFieldList())
        .thenReturn(Arrays.asList("missing", "dataset_id", "item_id"));
    LogMessageId id = extractor.extractMessageId(content);
    assertThat(id.getName()).isEqualTo("dataset_id");
    assertThat(id.getId()).isEqualTo("dataset_id");
  }

  @Test
  void extractMessageIdReturnsEmptyWhenNoFieldMatches() {
    when(ifConfig.getLogMessageIdFieldList()).thenReturn(Collections.singletonList("missing"));
    LogMessageId id = extractor.extractMessageId(content);
    assertThat(id.getName()).isNull();
    assertThat(id.getId()).isNull();
  }
}
