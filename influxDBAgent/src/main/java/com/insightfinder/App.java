package com.insightfinder;

import com.insightfinder.collector.InfluxDBMetricCollector;
import com.insightfinder.datamodel.InstanceData;
import com.insightfinder.payload.MetricDataBody;
import com.insightfinder.payload.MetricDataReceivePayload;
import com.insightfinder.service.IFProjectService;
import com.insightfinder.utilities.GsonUtility;
import com.insightfinder.utilities.HttpUtility;
import java.io.FileInputStream;
import java.io.IOException;
import java.net.http.HttpResponse;
import java.security.KeyManagementException;
import java.security.NoSuchAlgorithmException;
import java.util.Map;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;

public class App {

  public static final String DATA_RECEIVEENDPOINT_SUFFIX = "/api/v2/metric-data-receive";
  public static final String CHECK_AND_CREATE_PROJECT_SUFFIX = "/api/v1/check-and-add-custom-project";

  private static final Logger logger = Logger.getLogger(App.class.getName());
  private static final IFProjectService ifProjectService = new IFProjectService();

  public static void main(String[] args)
      throws IOException, InterruptedException, NoSuchAlgorithmException, KeyManagementException {
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

    String samplingInterval = prop.getProperty("insightfinder.samplingInterval");
    long fetchInterval = Long.parseLong(samplingInterval) * 60 * 1000;
    String projectName = prop.getProperty("insightfinder.projectName");
    String userName = prop.getProperty("insightfinder.userName");
    String licenseKey = prop.getProperty("insightfinder.licenseKey");
    String url = prop.getProperty("insightfinder.endpoint");
    String dataReceiveEndpoint = url + DATA_RECEIVEENDPOINT_SUFFIX;
    String projectEndpoint = url + CHECK_AND_CREATE_PROJECT_SUFFIX;

    if (!ifProjectService.checkProject(projectEndpoint, licenseKey, projectName, userName)) {
      String systemName = prop.getProperty("insightfinder.systemName");
      if (!ifProjectService.createProject(projectEndpoint, licenseKey, projectName, userName,
          systemName, samplingInterval)) {
        return;
      }
    }

    while (true) {
      long currentTimestamp = System.currentTimeMillis();
      logger.log(Level.INFO,
          "Start to collect data from " + lastFetchTimestamp + " to " + currentTimestamp);
      Map<String, InstanceData> dataMap = collector.collectData(0L, Long.MAX_VALUE);
      if (!dataMap.isEmpty()) {
        MetricDataReceivePayload payload = new MetricDataReceivePayload(projectName, userName,
            dataMap);
        MetricDataBody metricDataBody = new MetricDataBody(payload, licenseKey, userName);
        HttpResponse<String> response = HttpUtility.sendHttpRequest(dataReceiveEndpoint,
            GsonUtility.gson.toJson(metricDataBody));
        logger.log(Level.INFO, "Response: " + response.body());
      }
      lastFetchTimestamp = currentTimestamp;
      Thread.sleep(fetchInterval);
    }
  }
}
