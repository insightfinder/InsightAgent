package com.insightfinder.KafkaCollectorAgent.model;

import static org.assertj.core.api.Assertions.assertThat;

import com.insightfinder.KafkaCollectorAgent.model.logmessage.LogMessageId;
import org.junit.jupiter.api.Test;

public class ProjectListKeyTest {

  private LogMessageId id(String name, String value) {
    return LogMessageId.builder().name(name).id(value).build();
  }

  @Test
  void testNonDatasetIdFieldMatchedByPresence() {
    // master semantics: non-dataset_id fields match by presence only; the value is ignored.
    ProjectListKey key = ProjectListKey.parseFromString("_id:a1b2c3d4");
    assertThat(key.matchedMessageId(id("_id", "a1b2c3d4"))).isTrue();
    assertThat(key.matchedMessageId(id("_id", "other"))).isTrue();
    // a field the key does not declare does not match...
    assertThat(key.matchedMessageId(id("item_id", "x"))).isFalse();
    // ...except dataset_id, which matches any value when the key does not declare it (master quirk).
    assertThat(key.matchedMessageId(id("dataset_id", "a1b2c3d4"))).isTrue();
  }

  @Test
  void testDatasetNameMatchedByPresenceIgnoringValue() {
    // master matched dataset_name by presence only — the configured value is not compared.
    ProjectListKey key = ProjectListKey.parseFromString("dataset_name:DeviceStatus");
    assertThat(key.matchedMessageId(id("dataset_name", "DeviceStatus"))).isTrue();
    assertThat(key.matchedMessageId(id("dataset_name", "CPUEvent"))).isTrue();
  }

  @Test
  void testDatasetIdMatchedByValue() {
    ProjectListKey key = ProjectListKey.parseFromString("dataset_id:DS-1,item_id");
    assertThat(key.matchedMessageId(id("dataset_id", "DS-1"))).isTrue();
    assertThat(key.matchedMessageId(id("dataset_id", "DS-2"))).isFalse();
    assertThat(key.matchedMessageId(id("item_id", "any"))).isTrue();
    assertThat(key.matchedMessageId(id("dataset_name", "any"))).isFalse();
  }

  @Test
  void testNonDatasetIdValueDiscardedSoKeysDedup() {
    // master stored only presence for non-dataset_id fields, so keys differing only by a
    // dataset_name value are equal (they collapse in a map), matching master's de-duplication.
    assertThat(ProjectListKey.parseFromString("dataset_name:DeviceStatus"))
        .isEqualTo(ProjectListKey.parseFromString("dataset_name:CPUEvent"));
    // dataset_id values stay significant, so these remain distinct.
    assertThat(ProjectListKey.parseFromString("dataset_id:DS-1"))
        .isNotEqualTo(ProjectListKey.parseFromString("dataset_id:DS-2"));
  }

  @Test
  void testKeyWithoutDatasetIdMatchesAnyDatasetId() {
    // Restored master quirk: a key that never declares dataset_id matches every dataset_id message.
    ProjectListKey key = ProjectListKey.parseFromString("dataset_name:DeviceStatus");
    assertThat(key.matchedMessageId(id("dataset_id", "anything"))).isTrue();
  }
}
