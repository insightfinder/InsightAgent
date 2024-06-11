package com.insightfinder.kubeactions.config;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.kubeactions.client.websocket.WebSocketSessionHandler;
import org.jetbrains.annotations.NotNull;
import org.mapdb.DB;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.WebSocketConnectionManager;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;

@Configuration
public class WebSocketConfig {

  private static final Logger log = LoggerFactory.getLogger(WebSocketConfig.class);
  private static final String WEB_SOCKET_URL_PARAM = "wsUrl";
  private static final String CLIENT_ID_HEADER = "Client-Id";
  private static final int RECONNECT_DELAY = 5000;
  @Autowired
  private IFConfig ifConfig;
  @Autowired
  private DB mapDB;
  @Autowired
  private Gson gson;
  @Autowired
  private RestTemplate restTemplate;
  @Autowired
  private WebSocketSessionHandler webSocketSessionHandler;

  @Bean
  public WebSocketConnectionManager webSocketConnectionManager() {
    String webSocketUrl = getWebsocketServerUrl();
    if (webSocketUrl == null) {
      log.warn("Couldn't establish webSocket connection: fail to get webSocket server URL");
      return null;
    }
    WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
    headers.add(CLIENT_ID_HEADER, ifConfig.getActionServerId());
    //Generates a web socket connection
    WebSocketConnectionManager manager = new WebSocketConnectionManager(
        new StandardWebSocketClient(),
        webSocketSessionHandler,
        webSocketUrl);

    //Will connect as soon as possible
    manager.setAutoStartup(true);
    manager.setHeaders(headers);
    return manager;
  }

  private String getWebsocketServerUrl() {
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
