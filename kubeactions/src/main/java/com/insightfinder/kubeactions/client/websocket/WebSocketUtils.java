package com.insightfinder.kubeactions.client.websocket;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.kubeactions.config.IFConfig;
import org.jetbrains.annotations.NotNull;
import org.mapdb.DB;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

@Component
public class WebSocketUtils {

  private static final String WEB_SOCKET_URL_PARAM = "wsUrl";
  @Autowired
  private IFConfig ifConfig;
  @Autowired
  private DB mapDB;
  @Autowired
  private Gson gson;
  @Autowired
  private RestTemplate restTemplate;

  public String getWebsocketServerUrl() {
    String url = String.format("http://localhost:8080/api/v1/wss-agent-ops",
        ifConfig.getServerUrl());
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
    HttpEntity<MultiValueMap<String, String>> request = getMultiValueMapHttpEntity(headers);
    ResponseEntity<String> response = restTemplate.postForEntity(url, request, String.class);
    if (response.getStatusCode().is2xxSuccessful()) {
      JsonObject resObj = gson.fromJson(response.getBody(), JsonObject.class);
      return resObj.get(WEB_SOCKET_URL_PARAM).getAsString();
    }
    return null;
  }

  @NotNull
  private HttpEntity<MultiValueMap<String, String>> getMultiValueMapHttpEntity(
      HttpHeaders headers) {
    MultiValueMap<String, String> map = new LinkedMultiValueMap<>();
    map.add("userName", ifConfig.getUserName());
    map.add("systemName", ifConfig.getSystem());
    map.add("serverId", ifConfig.getActionServerId());
    map.add("ops", "startWss");
    return new HttpEntity<>(map, headers);
  }
}
