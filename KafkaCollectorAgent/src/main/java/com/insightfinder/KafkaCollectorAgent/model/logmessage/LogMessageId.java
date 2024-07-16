package com.insightfinder.KafkaCollectorAgent.model.logmessage;

import com.insightfinder.KafkaCollectorAgent.model.KafkaMessageId;
import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class LogMessageId implements KafkaMessageId {
  private String id;
  private String name;
}
