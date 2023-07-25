package com.insightfinder;

import com.insightfinder.collector.InfluxDBMetricCollector;
import com.insightfinder.datamodel.InstanceData;
import com.insightfinder.payload.MetricDataBody;
import com.insightfinder.payload.MetricDataReceivePayload;
import com.insightfinder.utilities.GsonUtility;
import com.insightfinder.utilities.HttpUtility;
import java.io.FileInputStream;
import java.io.IOException;
import java.net.http.HttpResponse;
import java.util.Map;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;

public class App {

  public static final String INSIGHTFINDER_ENDPOINT = "http://localhost:8080/api/v2/metric-data-receive";

  private static final Logger logger = Logger.getLogger(App.class.getName());

  public static void main(String[] args) throws IOException, InterruptedException {
    if (args.length < 1) {
      logger.log(Level.SEVERE, "config file parameter is missing");
      return;
    }
    String configFilePath = args[0];
    final Properties prop = new Properties();
    try (FileInputStream in = new FileInputStream(configFilePath)) {
      prop.load(in);
    }

    long lastFetchTimestamp = System.currentTimeMillis();
    InfluxDBMetricCollector collector = new InfluxDBMetricCollector(prop.getProperty("db.url"),
        prop.getProperty("db.username"), prop.getProperty("db.password"),
        prop.getProperty("db.query"));

    long fetchInterval = Long.parseLong(prop.getProperty("collecter.fetchinterval"));
    String projectName = prop.getProperty("insightfinder.projectName");
    String userName = prop.getProperty("insightfinder.userName");
    String samplingInterval = prop.getProperty("insightfinder.samplingInterval");
    String licenseKey = prop.getProperty("insightfinder.licenseKey");

    while (true) {
      long currentTimestamp = System.currentTimeMillis();
      logger.log(Level.INFO,
          "Start to collect data from " + lastFetchTimestamp + " to " + currentTimestamp);
      Map<String, InstanceData> dataMap = collector.collectData(0L, Long.MAX_VALUE);
      if (!dataMap.isEmpty()) {
        MetricDataReceivePayload payload = new MetricDataReceivePayload(projectName, userName,
            "influxDBAgent", samplingInterval, dataMap);
        MetricDataBody metricDataBody = new MetricDataBody(payload, licenseKey, userName);
        HttpResponse<String> response = HttpUtility.sendHttpRequest(INSIGHTFINDER_ENDPOINT,
            GsonUtility.gson.toJson(metricDataBody));
        logger.log(Level.INFO, "Response: " + response.body());
      }
      lastFetchTimestamp = currentTimestamp;
      Thread.sleep(fetchInterval);
    }
  }
}
