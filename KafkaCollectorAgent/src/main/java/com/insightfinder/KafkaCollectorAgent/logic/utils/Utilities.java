package com.insightfinder.KafkaCollectorAgent.logic.utils;

import com.google.gson.JsonObject;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.apache.commons.lang3.StringUtils;

public class Utilities {
  private static final Logger logger = Logger.getLogger(Utilities.class.getName());

  private static final String DOT = "\\.";
  public static final String JSON_KEY_DATASET_ID = "dataset_id";
  public static final String JSON_KEY_DATASET_NAME = "dataset_name";
  public static final String JSON_KEY_ITEM_ID = "item_id";

  public static String getKeyFromJson(JsonObject jsonObject, List<String> paths) {
    String value;
    if (jsonObject != null && paths != null) {
      for (String pathStr : paths) {
        JsonObject findValue = jsonObject;
        String[] pathArr = pathStr.split(DOT);
        for (int i = 0; i < pathArr.length; i++) {
          if (findValue.has(pathArr[i])) {
            if (findValue.get(pathArr[i]).isJsonObject()) {
              findValue = findValue.get(pathArr[i]).getAsJsonObject();
            } else {
              if (i == pathArr.length - 1) {
                value = findValue.get(pathArr[i]).getAsString();
                return value;
              } else {
                break;
              }
            }
          }
        }
      }
    }
    return null;
  }

  public static String getLastJsonKeyFromPath(String path) {
    if (!StringUtils.isEmpty(path)) {
      String[] pathElements = path.split(DOT);
      return pathElements[pathElements.length - 1];
    } else {
      return null;
    }
  }

  /**
   * Parse a timestamp that may arrive either as an epoch number (seconds or milliseconds, e.g.
   * {@code request_timestamp = 1780944255551}) or as a formatted date string (e.g.
   * {@code aip_time_stamp = "Jun 8, 2026 @ 18:44:15.551"}). Returns epoch milliseconds, or -1 if
   * the value cannot be parsed.
   */
  public static long getTimestampInMillis(String value, String format) {
    if (StringUtils.isEmpty(value)) {
      return -1;
    }
    String trimmed = value.trim();
    // Epoch timestamp: all digits. 10 digits or fewer are treated as seconds.
    if (trimmed.matches("\\d+")) {
      try {
        long epoch = Long.parseLong(trimmed);
        return trimmed.length() <= 10 ? epoch * 1000 : epoch;
      } catch (NumberFormatException e) {
        logger.log(Level.INFO, "can not parse epoch timestamp: " + trimmed);
        return -1;
      }
    }
    // Formatted date string.
    if (StringUtils.isEmpty(format)) {
      logger.log(Level.INFO, "no timestamp format configured for non-numeric timestamp: " + trimmed);
      return -1;
    }
    return getEpochMillisFromFormattedDate(trimmed, format);
  }

  public static long getGMTinHourFromMillis(String date, String format) {
    DateTimeFormatter rfc3339Formatter = DateTimeFormatter.ofPattern(format)
        .withResolverStyle(ResolverStyle.LENIENT);
    ZonedDateTime zonedDateTime = parseRfc3339(date, rfc3339Formatter);
    if (zonedDateTime != null) {
      return zonedDateTime.toInstant().toEpochMilli();
    }
    return -1;
  }

  public static ZonedDateTime parseRfc3339(String rfcDateTime, DateTimeFormatter rfc3339Formatter) {
    try {
      return ZonedDateTime.parse(rfcDateTime, rfc3339Formatter);
    } catch (DateTimeParseException exception) {
      logger.log(Level.INFO, " can not pare date :" + rfcDateTime);
    }
    return null;
  }

  /**
   * Convert a formatted date string to epoch milliseconds. Dates carrying a zone/offset (e.g.
   * {@code 2024-06-30T03:00:16+03:00}) are honored; zone-less dates (e.g.
   * {@code Jun 8, 2026 @ 18:44:15.551}) are assumed to be in UTC.
   */
  public static long getEpochMillisFromFormattedDate(String date, String format) {
    if (StringUtils.isEmpty(date) || StringUtils.isEmpty(format)) {
      return -1;
    }
    DateTimeFormatter formatter = DateTimeFormatter.ofPattern(format, Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.LENIENT);
    try {
      return ZonedDateTime.parse(date, formatter).toInstant().toEpochMilli();
    } catch (DateTimeParseException ignored) {
      // fall through and try parsing without a zone
    }
    try {
      return LocalDateTime.parse(date, formatter).toInstant(ZoneOffset.UTC).toEpochMilli();
    } catch (DateTimeParseException exception) {
      logger.log(Level.INFO, " can not parse date :" + date);
      return -1;
    }
  }

  public static String convertTimestampToMS(String timestamp) {
    StringBuilder stringBuilder = new StringBuilder();
    stringBuilder.append(timestamp);
    if (stringBuilder.length() == 10) {
      stringBuilder.append("000");
    }
    return stringBuilder.toString();
  }
}
