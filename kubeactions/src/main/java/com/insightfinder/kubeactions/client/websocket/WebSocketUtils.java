package com.insightfinder.kubeactions.client.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class WebSocketUtils {

  private static final Logger log = LoggerFactory.getLogger(WebSocketUtils.class);
  public static final String CLIENT_ID_HEADER = "Client-Id";
  public static final String WEB_SOCKET_SERVER_URL_TEMPLATE = "wss://%s/ws";
}
