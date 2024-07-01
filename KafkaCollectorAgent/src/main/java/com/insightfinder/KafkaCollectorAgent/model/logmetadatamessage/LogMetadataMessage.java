package com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.model.KafkaMessage;
import lombok.Builder;
import lombok.Data;
import org.springframework.lang.Nullable;

@Data
@Builder
public class LogMetadataMessage implements KafkaMessage {
  @Nullable private LogMetadataMessageId id;
  private JsonObject outputMessage;
}
