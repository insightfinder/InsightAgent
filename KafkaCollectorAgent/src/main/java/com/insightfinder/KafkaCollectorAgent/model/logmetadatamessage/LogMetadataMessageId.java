package com.insightfinder.KafkaCollectorAgent.model.logmetadatamessage;

import com.insightfinder.KafkaCollectorAgent.model.KafkaMessageId;
import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class LogMetadataMessageId implements KafkaMessageId {
  private String id;
  private String name;
}
