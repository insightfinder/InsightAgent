package com.insightfinder.KafkaCollectorAgent.model;

import com.google.gson.JsonObject;

public interface KafkaMessage {
  KafkaMessageId getId();
  JsonObject getOutputMessage();
}
