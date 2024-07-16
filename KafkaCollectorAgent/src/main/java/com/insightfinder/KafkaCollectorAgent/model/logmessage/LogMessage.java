package com.insightfinder.KafkaCollectorAgent.model.logmessage;

import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.model.KafkaMessage;
import lombok.Builder;
import lombok.Data;
import org.springframework.lang.Nullable;

@Data
@Builder
public class LogMessage implements KafkaMessage {
  @Nullable
  private LogMessageId id;
  private JsonObject outputMessage;
}
