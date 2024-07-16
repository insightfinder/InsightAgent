package com.insightfinder.collector;

import com.insightfinder.datamodel.InstanceData;
import java.security.KeyManagementException;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;
import okhttp3.OkHttpClient;
import org.influxdb.InfluxDB;
import org.influxdb.InfluxDBFactory;
import org.influxdb.dto.BoundParameterQuery.QueryBuilder;
import org.influxdb.dto.Query;
import org.influxdb.dto.QueryResult;
import org.influxdb.dto.QueryResult.Result;
import org.influxdb.dto.QueryResult.Series;

//https://github.com/influxdata/influxdb-java/blob/master/MANUAL.md
public class InfluxDBMetricCollector {

  String dbUrl;
  private final String userName;
  private final String password;
  private final String query;
  public static final String STARTTIMESTAMP = "startTimestamp";
  public static final String ENDTIMESTAMP = "endTimestamp";

  public InfluxDBMetricCollector(String dbUrl, String userName, String password, String query) {
    this.dbUrl = dbUrl;
    this.userName = userName;
    this.password = password;
    this.query = query;
  }

  public Map<String, InstanceData> collectData(long fromTimeMillis, long toTimeMillis)
      throws NoSuchAlgorithmException, KeyManagementException {
    final InfluxDB influxDB = InfluxDBFactory.connect(dbUrl, userName, password,
        getInsecureOkHttpClientBuilder());
    Query query = QueryBuilder.newQuery(this.query).bind(STARTTIMESTAMP, fromTimeMillis)
        .bind(ENDTIMESTAMP, toTimeMillis).create();
    QueryResult queryResult = influxDB.query(query);
    influxDB.close();
    Map<String, InstanceData> instanceDataMap = new HashMap<>();
    for (Result result : queryResult.getResults()) {
      for (Series series : result.getSeries()) {
        for (List<Object> values : series.getValues()) {
          long timestamp = Instant.parse(values.get(0).toString()).toEpochMilli();
          String metricName = values.get(1).toString();
          String instanceName = values.get(2).toString();
          Float value = Float.valueOf(values.get(3).toString());
          InstanceData instanceData = instanceDataMap.getOrDefault(instanceName,
              new InstanceData(instanceName, null));
          instanceData.addData(metricName, timestamp, value);
          instanceDataMap.put(instanceName, instanceData);
        }
      }
    }
    return instanceDataMap;
  }

  private OkHttpClient.Builder getSecureOkHttpClientBuilder() {
    return new OkHttpClient.Builder();
  }

  // use this for self-signed certificate
  private OkHttpClient.Builder getInsecureOkHttpClientBuilder()
      throws NoSuchAlgorithmException, KeyManagementException {
    TrustManager[] trustAllCerts = new TrustManager[]{
        new X509TrustManager() {
          @Override
          public void checkClientTrusted(java.security.cert.X509Certificate[] chain,
              String authType) {
          }

          @Override
          public void checkServerTrusted(java.security.cert.X509Certificate[] chain,
              String authType) {
          }

          @Override
          public java.security.cert.X509Certificate[] getAcceptedIssuers() {
            return new java.security.cert.X509Certificate[]{};
          }
        }
    };
    SSLContext sslContext = SSLContext.getInstance("SSL");
    sslContext.init(null, trustAllCerts, new java.security.SecureRandom());
    OkHttpClient.Builder builder = new OkHttpClient.Builder();
    builder.sslSocketFactory(sslContext.getSocketFactory(), (X509TrustManager) trustAllCerts[0]);
    builder.hostnameVerifier((hostname, session) -> true);
    return builder;
  }
}
