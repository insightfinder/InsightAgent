package com.insightfinder.KafkaCollectorAgent.model;

import static org.assertj.core.api.Assertions.assertThat;

import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import org.junit.jupiter.api.Test;

public class ProjectListKeyTest {

  private LogMessageId id(String name, String value) {
    return LogMessageId.builder().name(name).id(value).build();
  }

  @Test
  void testGenericFieldMatchWithValue() {
    ProjectListKey key = ProjectListKey.parseFromString("_id:a1b2c3d4");
    assertThat(key.matchedMessageId(id("_id", "a1b2c3d4"))).isTrue();
    assertThat(key.matchedMessageId(id("_id", "other"))).isFalse();
    // a different id field must not match a constraint defined for _id
    assertThat(key.matchedMessageId(id("dataset_id", "a1b2c3d4"))).isFalse();
  }

  @Test
  void testGenericFieldMatchAnyValue() {
    // no value after the field name means "match any value of this field"
    ProjectListKey key = ProjectListKey.parseFromString("client_request_id");
    assertThat(key.matchedMessageId(id("client_request_id", "482736195038472"))).isTrue();
    assertThat(key.matchedMessageId(id("client_request_id", "anything"))).isTrue();
    assertThat(key.matchedMessageId(id("_id", "anything"))).isFalse();
  }

  @Test
  void testBuiltInFieldsStillMatch() {
    ProjectListKey key = ProjectListKey.parseFromString("dataset_id:DS-1,item_id");
    assertThat(key.matchedMessageId(id("dataset_id", "DS-1"))).isTrue();
    assertThat(key.matchedMessageId(id("dataset_id", "DS-2"))).isFalse();
    assertThat(key.matchedMessageId(id("item_id", "any"))).isTrue();
    assertThat(key.matchedMessageId(id("dataset_name", "any"))).isFalse();
  }
}
