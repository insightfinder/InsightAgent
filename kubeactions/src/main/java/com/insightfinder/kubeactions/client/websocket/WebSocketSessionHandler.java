package com.insightfinder.kubeactions.client.websocket;

import com.insightfinder.InsightFinderAgent.proto.IfAgentInstructionWrapper.IfAgentInstruction;
import com.insightfinder.kubeactions.client.websocket.handler.K8sInstructionHandler;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.WebSocketConnectionManager;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;

@Component
public class WebSocketSessionHandler implements WebSocketHandler {

  private static final Logger log = LoggerFactory.getLogger(WebSocketSessionHandler.class);
  private static final int CONNECTION_RETRY_INTERVAL = 5;

  @Autowired
  private K8sInstructionHandler k8sInstructionHandler;
  private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
  @Autowired
  private WebSocketUtils webSocketUtils;
  private WebSocketConnectionManager connectionManager;

  public void setConnectionManager(WebSocketConnectionManager connectionManager) {
    this.connectionManager = connectionManager;
  }

  /**
   * Called when WS connects to the server.
   */
  @Override
  public void afterConnectionEstablished(WebSocketSession session) throws Exception {
    session.sendMessage(new TextMessage("Hello, server!"));
  }

  /**
   * Main method to handle server messages.
   */
  @Override
  public void handleMessage(WebSocketSession session, WebSocketMessage<?> message)
      throws Exception {
    if (message instanceof BinaryMessage binaryMessage) {
      IfAgentInstruction ifAgentInstruction = IfAgentInstruction.parseFrom(
          binaryMessage.getPayload());
      k8sInstructionHandler.handlerK8sInstruction(ifAgentInstruction);
    } else if (message instanceof TextMessage textMessage) {
    } else {
      log.warn("Unable to handle message: " + message.getClass());
    }
  }

  /**
   * Error handling.
   */
  @Override
  public void handleTransportError(WebSocketSession session, Throwable exception) throws Exception {
    log.error("WebSocket transport error: " + exception.getMessage());
    if (!connectionManager.isConnected()) {
      scheduleReconnection();
    }
  }

  /**
   * Called when WS is closed.
   */
  @Override
  public void afterConnectionClosed(WebSocketSession session, CloseStatus closeStatus)
      throws Exception {
    log.info("WebSocket connection closed, closeStatus: " + closeStatus.getReason());
    scheduleReconnection();
  }

  @Override
  public boolean supportsPartialMessages() {
    // TODO Auto-generated method stub
    return false;
  }

  private void scheduleReconnection() {
    scheduler.scheduleAtFixedRate(() -> {
      if (!connectionManager.isConnected()) {
        try {
          connectionManager.stop();
          String webSocketUrl = webSocketUtils.getWebsocketServerUrl();
          connectionManager = new WebSocketConnectionManager(
              new StandardWebSocketClient(),
              this,
              webSocketUrl);
          connectionManager.start();
        } catch (Exception e) {
          log.warn("Error when reconnecting webSocket: " + e.getMessage());
        }
      }
    }, CONNECTION_RETRY_INTERVAL, CONNECTION_RETRY_INTERVAL, TimeUnit.SECONDS);
  }
}
