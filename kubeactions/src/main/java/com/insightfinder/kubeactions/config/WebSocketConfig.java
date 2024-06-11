package com.insightfinder.kubeactions.config;

import com.insightfinder.kubeactions.client.websocket.WebSocketSessionHandler;
import com.insightfinder.kubeactions.client.websocket.WebSocketUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.WebSocketConnectionManager;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;

@Configuration
public class WebSocketConfig {
  private static final Logger log = LoggerFactory.getLogger(WebSocketConfig.class);
  private static final String CLIENT_ID_HEADER = "Client-Id";
  @Autowired
  IFConfig ifConfig;

  @Bean
  public WebSocketConnectionManager webSocketConnectionManager(
      WebSocketSessionHandler webSocketSessionHandler, WebSocketUtils webSocketUtils) {
    String webSocketUrl = webSocketUtils.getWebsocketServerUrl();
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
    webSocketSessionHandler.setConnectionManager(manager);
    return manager;
  }


}
