package com.insightfinder.KafkaCollectorAgent.logic.utils;

import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.convertTimestampToMS;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getGMTinHourFromMillis;
import static com.insightfinder.KafkaCollectorAgent.logic.utils.Utilities.getTimestampInMillis;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.ZoneId;
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
  public void testGetTimestampInMillisFromFormattedDateTwoDigitDay() {
    // "MMM d" must accept both single-digit (Jun 8) and two-digit (Jun 24) days
    String format = "MMM d, yyyy '@' HH:mm:ss.SSS";
    long jun8  = getTimestampInMillis("Jun 8, 2026 @ 00:00:00.000", format);
    long jun24 = getTimestampInMillis("Jun 24, 2026 @ 00:00:00.000", format);
    assertThat(jun8).isGreaterThan(0);
    assertThat(jun24 - jun8).isEqualTo(16L * 86_400_000);
  }

  @Test
  public void testGetTimestampInMillisWithTimezone() {
    String format = "MMM d, yyyy '@' HH:mm:ss.SSS";
    // Same wall-clock time in UTC vs America/New_York (EDT = UTC-4 in June)
    // → the NY interpretation is 4 hours later in absolute (UTC) time
    long utcMs = getTimestampInMillis("Jun 24, 2026 @ 10:00:00.000", format, ZoneId.of("UTC"));
    long nyMs  = getTimestampInMillis("Jun 24, 2026 @ 10:00:00.000", format,
        ZoneId.of("America/New_York"));
    assertThat(utcMs).isGreaterThan(0);
    assertThat(nyMs - utcMs).isEqualTo(4L * 3_600_000);
  }

  @Test
  public void testGetTimestampInMillisInvalid() {
    assertThat(getTimestampInMillis(null, "yyyy")).isEqualTo(-1);
    assertThat(getTimestampInMillis("not-a-date", null)).isEqualTo(-1);
    assertThat(getTimestampInMillis("not-a-date", "yyyy-MM-dd")).isEqualTo(-1);
  }
}
