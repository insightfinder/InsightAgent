package com.insightfinder.kubeactions.config;

import com.insightfinder.kubeactions.client.websocket.WebSocketSessionHandler;
import com.insightfinder.kubeactions.client.websocket.WebSocketUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.WebSocketConnectionManager;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;

public class WebSocketManager {

  private static final Logger log = LoggerFactory.getLogger(WebSocketManager.class);
  private static final String CLIENT_ID_HEADER = "Client-Id";
  private static WebSocketConnectionManager webSocketConnectionManager;

  public static WebSocketConnectionManager getWebSocketManager() {
    return webSocketConnectionManager;
  }

  public WebSocketConnectionManager initWebSocketConnectionManager(
      WebSocketSessionHandler webSocketSessionHandler, WebSocketUtils webSocketUtils,
      String serverId) {
    WebSocketConnectionManager manager;
    try {
      String webSocketUrl = webSocketUtils.getWebsocketServerUrl();
      WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
      headers.add(CLIENT_ID_HEADER, serverId);
      //Generates a web socket connection
      manager = new WebSocketConnectionManager(
          new StandardWebSocketClient(),
          webSocketSessionHandler,
          webSocketUrl);

      //Will connect as soon as possible
      manager.setAutoStartup(true);
      manager.setHeaders(headers);
      webSocketSessionHandler.setConnectionManager(manager);
      manager.start();
      webSocketConnectionManager = manager;
      return manager;
    } catch (Exception e) {
      log.warn("Error when initializing webSocket manager: " + e.getMessage());
      return null;
    }
  }
}
