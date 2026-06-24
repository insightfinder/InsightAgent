package com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.parser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.metricstreaming.MetricProjectConfigParser;
import com.insightfinder.KafkaCollectorAgent.model.ProjectInfo;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class LenovoMetricMessageParserTest {

  @Mock
  IFConfig ifConfig;
  @Mock
  MetricProjectConfigParser metricProjectConfigParser;

  LenovoMetricMessageParser parser;

  @BeforeEach
  void setup() {
    when(ifConfig.getDataFormat()).thenReturn("String");
    when(ifConfig.getDataFormatRegex()).thenReturn(
        "(?<project>\\w+),(?<instance>\\w+),(?<timestamp>\\d+),(?<metric>\\w+),(?<value>[\\d.]+)");
    when(ifConfig.getMetricRegex()).thenReturn(".*");
    when(ifConfig.getProjectList()).thenReturn("non-empty");
    Set<String> instances = new HashSet<>();
    instances.add("inst1");
    when(ifConfig.getInstanceList()).thenReturn(instances);
    when(ifConfig.getProjectKey()).thenReturn("project");
    when(ifConfig.getInstanceKey()).thenReturn("instance");
    when(ifConfig.getTimestampKey()).thenReturn("timestamp");
    when(ifConfig.getMetricKey()).thenReturn("metric");
    when(ifConfig.getValueKey()).thenReturn("value");
    when(ifConfig.getProjectDelimiter()).thenReturn("\\|");
    Map<String, ProjectInfo> mapping = new HashMap<>();
    mapping.put("proj1", ProjectInfo.builder().project("IFProj").system("IFSys").build());
    when(metricProjectConfigParser.getMetricProjectMapping()).thenReturn(mapping);

    parser = new LenovoMetricMessageParser(ifConfig, metricProjectConfigParser);
    parser.init();
  }

  @Test
  void parsesRegexMetricIntoRecord() {
    List<MetricRecord> records = parser.parse("proj1,inst1,1719705616000,cpu,12.5");
    assertThat(records).hasSize(1);
    MetricRecord record = records.get(0);
    assertThat(record.getProjectInfo())
        .isEqualTo(ProjectInfo.builder().project("IFProj").system("IFSys").build());
    assertThat(record.getInstanceName()).isEqualTo("inst1");
    assertThat(record.getTimestamp()).isEqualTo(1719705616000L);
    assertThat(record.getMetricName()).isEqualTo("cpu");
    assertThat(record.getValue()).isEqualTo(12.5);
  }

  @Test
  void returnsEmptyWhenInstanceNotInList() {
    assertThat(parser.parse("proj1,other,1719705616000,cpu,12.5")).isEmpty();
  }

  @Test
  void returnsEmptyWhenProjectNotInProjectList() {
    assertThat(parser.parse("unknownProj,inst1,1719705616000,cpu,12.5")).isEmpty();
  }

  @Test
  void returnsEmptyWhenRegexDoesNotMatch() {
    assertThat(parser.parse("this is not a metric line")).isEmpty();
  }

  @Test
  void jsonModeReturnsEmpty() {
    when(ifConfig.getDataFormat()).thenReturn("JSON");
    parser.init();
    assertThat(parser.parse("{\"any\":\"json\"}")).isEmpty();
  }
}
