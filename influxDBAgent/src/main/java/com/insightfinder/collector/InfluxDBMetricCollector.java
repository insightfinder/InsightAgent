package com.insightfinder.collector;

import com.insightfinder.datamodel.InstanceData;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.influxdb.InfluxDB;
import org.influxdb.InfluxDBFactory;
import org.influxdb.dto.BoundParameterQuery.QueryBuilder;
import org.influxdb.dto.Query;
import org.influxdb.dto.QueryResult;
import org.influxdb.dto.QueryResult.Result;
import org.influxdb.dto.QueryResult.Series;

//https://github.com/influxdata/influxdb-java/blob/master/MANUAL.md
public class InfluxDBMetricCollector {

  public static final String INSIGHTFINDER_ENDPOINT = "/api/v2/metric-data-receive";

  String dbUrl;
  private final String userName;
  private final String password;
  private final String queryURL;
  public static final String STARTTIMESTAMP = "startTimestamp";
  public static final String ENDTIMESTAMP = "endTimestamp";

  public InfluxDBMetricCollector(String dbUrl, String userName, String password, String queryURL) {
    this.dbUrl = dbUrl;
    this.userName = userName;
    this.password = password;
    this.queryURL = queryURL;
  }

  public Map<String, InstanceData> collectData(long fromTimeMillis, long toTimeMillis) {
    final InfluxDB influxDB = InfluxDBFactory.connect(dbUrl, userName, password);
    Query query = QueryBuilder.newQuery(queryURL).bind(STARTTIMESTAMP, fromTimeMillis)
        .bind(ENDTIMESTAMP, toTimeMillis).create();
    QueryResult queryResult = influxDB.query(query);
    influxDB.close();
    Map<String, InstanceData> instanceDataMap = new HashMap<>();
    for (Result result : queryResult.getResults()) {
      for (Series series : result.getSeries()) {
        System.out.println("full result " + series.getValues());
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
    System.out.println(instanceDataMap);
    return instanceDataMap;
  }
}
