package com.insightfinder.KafkaCollectorAgent.logic.utils;

import com.google.gson.JsonObject;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
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

  public static String convertTimestampToMS(String timestamp) {
    StringBuilder stringBuilder = new StringBuilder();
    stringBuilder.append(timestamp);
    if (stringBuilder.length() == 10) {
      stringBuilder.append("000");
    }
    return stringBuilder.toString();
  }
}
