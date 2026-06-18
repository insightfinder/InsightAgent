package com.insightfinder.KafkaCollectorAgent.logic.utils;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.convertTimestampToMS;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getGMTinHourFromMillis;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getTimestampInMillis;
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

  @Test
  public void testGetTimestampInMillisFromEpoch() {
    // epoch milliseconds (request_timestamp) is returned as-is
    assertThat(getTimestampInMillis("1780944255551", null)).isEqualTo(1780944255551L);
    // epoch seconds (10 digits) are converted to milliseconds
    assertThat(getTimestampInMillis("1780944255", null)).isEqualTo(1780944255000L);
  }

  @Test
  public void testGetTimestampInMillisFromFormattedDate() {
    // zone-less, English month name (aip_time_stamp) is parsed assuming UTC
    String format = "MMM d, yyyy '@' HH:mm:ss.SSS";
    assertThat(getTimestampInMillis("Jun 8, 2026 @ 18:44:15.551", format))
        .isEqualTo(1780944255551L);
  }

  @Test
  public void testGetTimestampInMillisInvalid() {
    assertThat(getTimestampInMillis(null, "yyyy")).isEqualTo(-1);
    assertThat(getTimestampInMillis("not-a-date", null)).isEqualTo(-1);
    assertThat(getTimestampInMillis("not-a-date", "yyyy-MM-dd")).isEqualTo(-1);
  }
}
