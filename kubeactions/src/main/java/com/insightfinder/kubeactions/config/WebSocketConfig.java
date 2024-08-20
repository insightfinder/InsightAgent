package com.insightfinder.kubeactions.config;

import static com.insightfinder.kubeactions.client.websocket.WebSocketUtils.CLIENT_ID_HEADER;

import com.insightfinder.kubeactions.client.websocket.WebSocketSessionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.WebSocketConnectionManager;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;

@Configuration
public class WebSocketConfig {

  private static final Logger log = LoggerFactory.getLogger(WebSocketConfig.class);
  @Autowired
  IFConfig ifConfig;

  @Bean
  @Qualifier("webSocketConnectionManager")
  public WebSocketConnectionManager webSocketConnectionManager(
      WebSocketSessionHandler webSocketSessionHandler) {
    WebSocketConnectionManager manager;
    String webSocketUrl = ifConfig.getServerWebSocketUrl();
    WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
    headers.add(CLIENT_ID_HEADER, ifConfig.getActionServerId());
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
    return manager;
  }
}
