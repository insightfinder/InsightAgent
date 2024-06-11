package com.insightfinder.kubeactions.client.websocket.handler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.client.WebSocketConnectionManager;

@Component
public class WebSocketConnectionCloseHandler {

  private static final Logger log = LoggerFactory.getLogger(WebSocketConnectionCloseHandler.class);

  @Autowired
  private WebSocketConnectionManager webSocketConnectionManager;

  public void reconnect() {
//    new Thread(() -> {
//      while (!Thread.currentThread().isInterrupted()) {
//        try {
//          Thread.sleep(RECONNECT_DELAY);
//          if (!webSocketConnectionManager.isConnected()) {
//            log.info("Attempting to reconnect...");
//            webSocketConnectionManager.start();
//          } else {
//            break;
//          }
//        } catch (InterruptedException e) {
//          Thread.currentThread().interrupt();
//        }
//      }
//    }).start();
  }
}
