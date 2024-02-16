package com.insightfinder.service;

import java.io.IOException;
import java.util.logging.Level;
import java.util.logging.Logger;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.json.JSONObject;

public class IFProjectService {

  public static final String METRIC_DATA_TYPE = "Metric";
  public static final String CUSTOM_AGENT_TYPE = "Custom";
  private static final OkHttpClient client = new OkHttpClient();
  private static final Logger logger = Logger.getLogger(IFProjectService.class.getName());

  public boolean checkProject(String endpoint, String licenseKey, String projectName,
      String userName) throws IOException {

    RequestBody formBody = new FormBody.Builder()
        .add("userName", userName)
        .add("licenseKey", licenseKey)
        .add("projectName", projectName)
        .add("operation", "check")
        .build();

    Request request = new Request.Builder()
        .url(endpoint)
        .post(formBody)
        .build();

    Response response = client.newCall(request).execute();
    JSONObject json = new JSONObject(response.body().string());
    return json.has("isProjectExist") && json.getBoolean("isProjectExist");
  }

  public boolean createProject(String endpoint, String licenseKey, String projectName,
      String userName, String systemName, String samplingInterval) throws IOException {
    RequestBody formBody = new FormBody.Builder()
        .add("userName", userName)
        .add("licenseKey", licenseKey)
        .add("projectName", projectName)
        .add("operation", "create")
        .add("instanceType", "PrivateCloud")
        .add("projectCloudType", "PrivateCloud")
        .add("samplingInterval", samplingInterval)
        .add("systemName", systemName)
        .add("dataType", METRIC_DATA_TYPE)
        .add("insightAgentType", CUSTOM_AGENT_TYPE)
        .build();

    Request request = new Request.Builder()
        .url(endpoint)
        .post(formBody)
        .build();

    Response response = client.newCall(request).execute();
    JSONObject json = new JSONObject(response.body().string());
    if (json.has("success") && json.getBoolean("success")) {
      logger.log(Level.INFO, "Successfully created project " + projectName);
      return true;
    }
    logger.log(Level.INFO, "Failed to create project " + projectName);
    return false;
  }
}
