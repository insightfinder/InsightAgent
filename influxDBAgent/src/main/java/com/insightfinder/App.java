package com.insightfinder;

import com.insightfinder.collector.InfluxDBMetricCollector;
import com.insightfinder.datamodel.InstanceData;
import com.insightfinder.datamodel.MetricDataPoint;
import com.insightfinder.payload.MetricDataReceivePayload;
import java.io.IOException;
import java.util.Map;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;

public class App {

  private static final Logger logger = Logger.getLogger(App.class.getName());

  public static void main(String[] args) throws IOException, InterruptedException {
    long lastFetchTimestamp = System.currentTimeMillis();

    Properties prop = new Properties();
    prop.load(App.class.getClassLoader().getResourceAsStream("config.properties"));

    InfluxDBMetricCollector collector = new InfluxDBMetricCollector(prop.getProperty("db.url"),
        prop.getProperty("db.username"), prop.getProperty("db.password"),
        prop.getProperty("db.query"));

    long fetchInterval = Long.parseLong(prop.getProperty("collecter.fetchinterval"));
    String projectName = prop.getProperty("insightfinder.projectName");
    String userName = prop.getProperty("insightfinder.userName");
    String samplingInterval = prop.getProperty("insightfinder.samplingInterval");

    while (true) {
      Thread.sleep(fetchInterval);
      long currentTimestamp = System.currentTimeMillis();
      logger.log(Level.INFO,
          "Start to collect data from " + lastFetchTimestamp + " to " + currentTimestamp);
      Map<String, InstanceData> dataMap = collector.collectData(0L, Long.MAX_VALUE);
      MetricDataReceivePayload payload = new MetricDataReceivePayload(projectName, userName,
          "influxDBAgent", samplingInterval, dataMap);
      lastFetchTimestamp = currentTimestamp;
    }
  }
}
