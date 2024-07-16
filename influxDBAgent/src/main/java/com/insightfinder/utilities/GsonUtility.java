package com.insightfinder.utilities;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.stream.JsonReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.lang.reflect.Type;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.zip.GZIPInputStream;
import org.apache.http.util.TextUtils;

public class GsonUtility {

  private static final String WARNING_MSG = "Fail to convert the string: %s to the class: %s";
  public static Gson gson = new GsonBuilder().enableComplexMapKeySerialization()
      .setDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ").serializeSpecialFloatingPointValues().create();
  private static final Logger LOGGER = Logger.getLogger(GsonUtility.class.getName());

  public static <T> ByteBuffer zipJson(T obj, Gson gson) {
    ByteArrayOutputStream bout = new ByteArrayOutputStream();
    Writer writer = new OutputStreamWriter(bout, StandardCharsets.ISO_8859_1);
    gson.toJson(obj, writer);
    try {
      writer.close();
      bout.close();
    } catch (IOException e) {
      e.printStackTrace();
    }
    byte[] array = bout.toByteArray();
    return GzipUtil.zip(array);
  }

  public static <T> ByteBuffer zipJson(T obj, Gson gson, Type type) {
    ByteArrayOutputStream bout = new ByteArrayOutputStream();
    Writer writer = new OutputStreamWriter(bout, StandardCharsets.ISO_8859_1);
    gson.toJson(obj, type, writer);
    try {
      writer.close();
      bout.close();
    } catch (IOException e) {
      e.printStackTrace();
    }
    byte[] array = bout.toByteArray();
    return GzipUtil.zip(array);
  }

  public static <T> ByteBuffer zipJson(T obj) {
    return zipJson(obj, gson);
  }

  public static <T> T unzipJson(ByteBuffer byteBuffer, Class<T> clazz) {
    return unzipJson(byteBuffer, clazz, gson);
  }

  public static <T> T unzipJson(ByteBuffer byteBuffer, Class<T> clazz, Gson gson) {
    if (byteBuffer != null) {
      byte[] compressed = byteBuffer.array();
      if (compressed.length == 0) {
        throw new IllegalArgumentException("Cannot unzip null or empty bytes");
      }
      if (!GzipUtil.isZipped(compressed)) {
        return null;
      }
      try (ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressed)) {
        try (GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream)) {
          try (InputStreamReader inputStreamReader = new InputStreamReader(gzipInputStream,
              StandardCharsets.ISO_8859_1)) {
            try (JsonReader jsonReader = new JsonReader(inputStreamReader)) {
              T ret = gson.fromJson(jsonReader, clazz);
              jsonReader.close();
              inputStreamReader.close();
              gzipInputStream.close();
              byteArrayInputStream.close();
              return ret;
            }
          }
        }
      } catch (IOException e) {
        throw new RuntimeException("Failed to unzip content with gson", e);
      }
    }
    return null;
  }

  public static <T> List<T> unzipJson(ByteBuffer byteBuffer, Type type) {
    return unzipJson(byteBuffer, type, gson);
  }

  public static <T> Set<T> unzipJsonSet(ByteBuffer byteBuffer, Type type) {
    return unzipJsonSet(byteBuffer, type, gson);
  }

  public static <T> Set<T> unzipJsonSet(ByteBuffer byteBuffer, Type type, Gson gson) {
    if (byteBuffer != null) {
      byte[] compressed = byteBuffer.array();
      if (compressed.length == 0) {
        throw new IllegalArgumentException("Cannot unzip null or empty bytes");
      }
      if (!GzipUtil.isZipped(compressed)) {
        return null;
      }
      try (ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressed)) {
        try (GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream)) {
          try (InputStreamReader inputStreamReader = new InputStreamReader(gzipInputStream,
              StandardCharsets.ISO_8859_1)) {
            try (JsonReader jsonReader = new JsonReader(inputStreamReader)) {
              Set<T> ret = gson.fromJson(jsonReader, type);
              jsonReader.close();
              inputStreamReader.close();
              gzipInputStream.close();
              byteArrayInputStream.close();
              return ret;
            }
          }
        }
      } catch (IOException e) {
        throw new RuntimeException("Failed to unzip content with gson", e);
      }
    }
    return null;
  }

  public static <K, V> Map<K, V> unzipJsonMap(ByteBuffer byteBuffer, Type type) {
    return unzipJsonMap(byteBuffer, type, gson);
  }

  public static <K, V> Map<K, V> unzipJsonMap(ByteBuffer byteBuffer, Type type, Gson gson) {
    if (byteBuffer != null) {
      byte[] compressed = byteBuffer.array();
      if (compressed.length == 0) {
        throw new IllegalArgumentException("Cannot unzip null or empty bytes");
      }
      if (!GzipUtil.isZipped(compressed)) {
        return null;
      }
      try (ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressed)) {
        try (GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream)) {
          try (InputStreamReader inputStreamReader = new InputStreamReader(gzipInputStream,
              StandardCharsets.ISO_8859_1)) {
            try (JsonReader jsonReader = new JsonReader(inputStreamReader)) {
              Map<K, V> ret = gson.fromJson(jsonReader, type);
              jsonReader.close();
              inputStreamReader.close();
              gzipInputStream.close();
              byteArrayInputStream.close();
              return ret;
            }
          }
        }
      } catch (IOException e) {
        throw new RuntimeException("Failed to unzip content with gson", e);
      }
    }
    return null;
  }

  public static <T> List<T> unzipJson(ByteBuffer byteBuffer, Type type, Gson gson) {
    if (byteBuffer != null) {
      byte[] compressed = byteBuffer.array();
      if (compressed.length == 0) {
        throw new IllegalArgumentException("Cannot unzip null or empty bytes");
      }
      if (!GzipUtil.isZipped(compressed)) {
        return null;
      }
      try (ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressed)) {
        try (GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream)) {
          try (InputStreamReader inputStreamReader = new InputStreamReader(gzipInputStream,
              StandardCharsets.ISO_8859_1)) {
            try (JsonReader jsonReader = new JsonReader(inputStreamReader)) {
              List<T> ret = gson.fromJson(jsonReader, type);
              jsonReader.close();
              inputStreamReader.close();
              gzipInputStream.close();
              byteArrayInputStream.close();
              return ret;
            }
          }
        }
      } catch (IOException e) {
        throw new RuntimeException("Failed to unzip content with gson", e);
      }
    }
    return null;
  }

  public static <T> List<T> convertToList(String listString, Type type, Class<T> clazz) {
    List<T> list = new ArrayList<>();
    try {
      if (!TextUtils.isEmpty(listString)) {
        list = gson.fromJson(listString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to list", e);
    }
    return list;
  }

  public static <T> List<T> convertToList(String listString, Type type) {
    List<T> list = new ArrayList<>();
    try {
      if (!TextUtils.isEmpty(listString)) {
        list = gson.fromJson(listString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to list", e);
    }
    return list;
  }

  public static <T> Set<T> convertToSet(String setString, Type type, Class<T> clazz) {
    Set<T> set = new HashSet<>();
    try {
      if (!TextUtils.isEmpty(setString)) {
        set = gson.fromJson(setString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to set", e);
    }
    return set;
  }

  public static <T> TreeSet<T> convertToTreeSet(String setString, Type type, Class<T> clazz) {
    TreeSet<T> set = new TreeSet<>();
    try {
      if (!TextUtils.isEmpty(setString)) {
        set = gson.fromJson(setString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to set", e);
    }
    return set;
  }

  public static <T> Map<T, T> convertToMap(String mapString, Type type, Class<T> clazz) {
    Map<T, T> map = new HashMap<>();
    try {
      if (!TextUtils.isEmpty(mapString)) {
        map = gson.fromJson(mapString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to map", e);
    }
    return map;
  }

  public static <T> Map<T, List<T>> convertToMapWithList(String mapString, Type type,
      Class<T> clazz) {
    Map<T, List<T>> map = new HashMap<>();
    try {
      if (!TextUtils.isEmpty(mapString)) {
        map = gson.fromJson(mapString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to map", e);
    }
    return map;
  }

  public static <T> TreeMap<T, T> convertToTreeMap(String mapString, Type type, Class<T> clazz) {
    TreeMap<T, T> map = new TreeMap<>();
    try {
      if (!TextUtils.isEmpty(mapString)) {
        map = gson.fromJson(mapString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to map", e);
    }
    return map;
  }

  public static <T, E> Map<T, E> convertToMap(String mapString, Type type, Class<T> clazz1,
      Class<E> clazz2) {
    Map<T, E> map = new HashMap<>();
    try {
      if (!TextUtils.isEmpty(mapString)) {
        map = gson.fromJson(mapString, type);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, "Fail to convert the gson string to map", e);
    }
    return map;
  }

  public static <T> T fromJson(String str, Class<T> clazz) {
    try {
      if (!TextUtils.isEmpty(str)) {
        return gson.fromJson(str, clazz);
      }
    } catch (Exception e) {
      LOGGER.log(Level.WARNING, String.format(WARNING_MSG, str, clazz.getName()));
    }
    return null;
  }

  public static Gson createExposeGson() {
    return new GsonBuilder().excludeFieldsWithoutExposeAnnotation()
        .enableComplexMapKeySerialization().create();
  }
}
