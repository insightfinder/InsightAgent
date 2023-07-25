package com.insightfinder.utilities;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.Buffer;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import org.apache.http.util.TextUtils;

public class GzipUtil {

  public static ByteBuffer zip(final String str) {
    if ((str == null) || (str.length() == 0)) {
      throw new IllegalArgumentException("Cannot zip null or empty string");
    }
    byte[] uncompressedData = str.getBytes(StandardCharsets.ISO_8859_1);
    return zip(uncompressedData);
  }

  public static ByteBuffer zip(final byte[] uncompressedData) {
    ByteBuffer result = null;
    try (ByteArrayOutputStream bos = new ByteArrayOutputStream(uncompressedData.length);
        GZIPOutputStream gzipOS = new GZIPOutputStream(bos)) {
      gzipOS.write(uncompressedData);
      // You need to close it before using bos
      gzipOS.close();
      result = ByteBuffer.wrap(bos.toByteArray());
    } catch (IOException e) {
      throw new RuntimeException("Failed to zip content", e);
    }
    return result;
  }

  /**
   * Compressed the string into byte array
   *
   * @param str
   * @return
   */
  public static byte[] zipToByteArray(final String str) {
    if ((str == null) || (str.length() == 0)) {
      throw new IllegalArgumentException("Cannot zip null or empty string");
    }
    byte[] uncompressedData = str.getBytes(StandardCharsets.ISO_8859_1);
    byte[] result = null;
    try (ByteArrayOutputStream bos = new ByteArrayOutputStream(uncompressedData.length);
        GZIPOutputStream gzipOS = new GZIPOutputStream(bos)) {
      gzipOS.write(uncompressedData);
      // You need to close it before using bos
      gzipOS.close();
      result = bos.toByteArray();
    } catch (IOException e) {
      throw new RuntimeException("Failed to zip content", e);
    }
    return result;
  }

  public static ByteBuffer zip(final ByteBuffer byteBuffer) {
    if ((byteBuffer == null)) {
      throw new IllegalArgumentException("Cannot zip null or empty byte buffer");
    }
    return zip(byteBuffer.array());
  }

  public static String zipString(final String str) {
    if ((str == null) || (str.length() == 0)) {
      throw new IllegalArgumentException("Cannot zip null or empty string");
    }
    String result = null;
    byte[] uncompressedData = str.getBytes(StandardCharsets.ISO_8859_1);
    try (ByteArrayOutputStream bos = new ByteArrayOutputStream(uncompressedData.length);
        GZIPOutputStream gzipOS = new GZIPOutputStream(bos)) {
      gzipOS.write(uncompressedData);
      // You need to close it before using bos
      gzipOS.close();
      result = bos.toString();
    } catch (IOException e) {
      throw new RuntimeException("Failed to zip content", e);
    }
    return result;
  }

  public static String unzip(ByteBuffer byteBuffer) {
    return unzip(byteBuffer.array());
  }

  public static String unzip(final byte[] compressed) {
    if ((compressed == null) || (compressed.length == 0)) {
      throw new IllegalArgumentException("Cannot unzip null or empty bytes");
    }
    if (!isZipped(compressed)) {
      return new String(compressed);
    }
    try (ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressed)) {
      try (GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream)) {
        try (InputStreamReader inputStreamReader = new InputStreamReader(gzipInputStream,
            StandardCharsets.ISO_8859_1)) {
          try (BufferedReader bufferedReader = new BufferedReader(inputStreamReader)) {
            StringBuilder output = new StringBuilder();
            String line;
            while ((line = bufferedReader.readLine()) != null) {
              output.append(line);
              output.append("\n");
            }
            bufferedReader.close();
            inputStreamReader.close();
            gzipInputStream.close();
            byteArrayInputStream.close();
            return output.toString();
          }
        }
      }
    } catch (IOException e) {
      throw new RuntimeException("Failed to unzip content", e);
    }
  }

  public static String unzipWithoutNewLine(ByteBuffer byteBuffer) {
    return unzip(byteBuffer.array());
  }

  public static String unzipWithoutNewLine(final byte[] compressed) {
    if ((compressed == null) || (compressed.length == 0)) {
      throw new IllegalArgumentException("Cannot unzip null or empty bytes");
    }
    if (!isZipped(compressed)) {
      return new String(compressed);
    }
    try (ByteArrayInputStream byteArrayInputStream = new ByteArrayInputStream(compressed)) {
      try (GZIPInputStream gzipInputStream = new GZIPInputStream(byteArrayInputStream)) {
        try (InputStreamReader inputStreamReader = new InputStreamReader(gzipInputStream,
            StandardCharsets.ISO_8859_1)) {
          try (BufferedReader bufferedReader = new BufferedReader(inputStreamReader)) {
            StringBuilder output = new StringBuilder();
            String line;
            while ((line = bufferedReader.readLine()) != null) {
              output.append(line);
            }
            bufferedReader.close();
            inputStreamReader.close();
            gzipInputStream.close();
            byteArrayInputStream.close();
            return output.toString();
          }
        }
      }
    } catch (IOException e) {
      throw new RuntimeException("Failed to unzip content", e);
    }
  }

  public static boolean isZipped(final byte[] compressed) {
    return (compressed[0] == (byte) (GZIPInputStream.GZIP_MAGIC))
        && (compressed[1] == (byte) (GZIPInputStream.GZIP_MAGIC >> 8));
  }

  public static <E> E decompressModel(ByteBuffer content, Class<E> targetClass) {
    if (content != null) {
      String unzipContent = null;
      try {
        unzipContent = GzipUtil.unzip(content);
      } catch (Exception e) {
        Logger.getLogger(targetClass.getName())
            .log(Level.WARNING, "Exception When decompress", e);
      }
      if (!TextUtils.isEmpty(unzipContent)) {
        return GsonUtility.gson.fromJson(unzipContent, targetClass);
      }
    }
    return null;
  }

  public static ByteBuffer merge(List<ByteBuffer> byteBuffers) {
    if (byteBuffers == null || byteBuffers.size() == 0) {
      return ByteBuffer.allocate(0);
    } else if (byteBuffers.size() == 1) {
      return byteBuffers.get(0);
    } else {
      ByteBuffer fullContent = ByteBuffer.allocate(
          byteBuffers.stream()
              .mapToInt(Buffer::capacity)
              .sum()
      );
      byteBuffers.forEach(fullContent::put);
      fullContent.flip();
      return fullContent;
    }
  }
}