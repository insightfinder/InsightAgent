package com.insightfinder.KafkaCollectorAgent.logic.utils;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.convertTimestampToMS;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getGMTinHourFromMillis;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

public class UtilitiesTest {

  @Test
  public void testMSTimestampConverter() {
    String timestamp = convertTimestampToMS("10000000000");
    assertThat(timestamp.length()).isGreaterThan(10);
  }

  @Test
  public void testDateTimeConvertor() {
    String dateFormat = "yyyy-MM-dd'T'HH:mm:ssZZZZZ";
    String dateTime = "2023-02-24T07:22:23-05:00";
    long time = getGMTinHourFromMillis(dateTime, dateFormat);
    assertThat(time).isGreaterThan(0);
    String dateTime2 = "2023-02-24T07:22:23";
    time = getGMTinHourFromMillis(dateTime2, dateFormat);
    assertThat(time).isEqualTo(-1);
  }
}
