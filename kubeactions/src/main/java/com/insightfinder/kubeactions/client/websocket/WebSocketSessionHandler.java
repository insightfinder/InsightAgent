package com.insightfinder.kubeactions.client.websocket;

import static com.insightfinder.kubeactions.client.websocket.WebSocketUtils.CLIENT_ID_HEADER;

import com.insightfinder.InsightFinderAgent.proto.IfAgentInstructionWrapper.IfAgentInstruction;
import com.insightfinder.InsightFinderAgent.proto.PingWrapper.Ping;
import com.insightfinder.InsightFinderAgent.proto.RootWrapper.Root;
import com.insightfinder.kubeactions.client.websocket.handler.K8sInstructionHandler;
import com.insightfinder.kubeactions.config.IFConfig;
import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.PongMessage;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.WebSocketConnectionManager;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;

@Component
public class WebSocketSessionHandler implements WebSocketHandler {

  private static final Logger log = LoggerFactory.getLogger(WebSocketSessionHandler.class);
  private static final int CONNECTION_RETRY_INTERVAL = 10;
  private static final int HEART_BEAT_INTERVAL = 10;

  @Autowired
  private K8sInstructionHandler k8sInstructionHandler;
  private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
  @Autowired
  private IFConfig ifConfig;
  @Autowired
  private ConfigurableApplicationContext context;
  private WebSocketConnectionManager connectionManager;

  public void setConnectionManager(WebSocketConnectionManager connectionManager) {
    this.connectionManager = connectionManager;
  }

  private ScheduledFuture<?> scheduledFuture;

  /**
   * Called when WS connects to the server.
   */
  @Override
  public void afterConnectionEstablished(WebSocketSession session) throws Exception {
    session.sendMessage(new TextMessage("Hello, server!"));
    startHartBeat(session);
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
    } else if (message instanceof TextMessage) {
    } else if (message instanceof PongMessage) {
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
      stopHeartbeat();
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
    stopHeartbeat();
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
          String webSocketUrl = ifConfig.getServerWebSocketUrl();
          ConfigurableListableBeanFactory beanFactory = context.getBeanFactory();
          ((DefaultListableBeanFactory) beanFactory).destroySingleton("webSocketConnectionManager");
          connectionManager = new WebSocketConnectionManager(
              new StandardWebSocketClient(),
              this,
              webSocketUrl);
          beanFactory.registerSingleton("webSocketConnectionManager", connectionManager);
          log.debug("Attempt to reconnect webSocket");
          WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
          headers.add(CLIENT_ID_HEADER, ifConfig.getActionServerId());
          connectionManager.setHeaders(headers);
          connectionManager.start();
        } catch (Exception e) {
          log.warn("Error when reconnecting webSocket: " + e.getMessage());
        }
      }
    }, CONNECTION_RETRY_INTERVAL, CONNECTION_RETRY_INTERVAL, TimeUnit.SECONDS);
  }

  private void startHartBeat(WebSocketSession session) {
    scheduledFuture = scheduler.scheduleAtFixedRate(() -> {
      try {
        Ping ping = Ping.newBuilder().setPingNum(0).build();
        Root root = Root.newBuilder().setPing(ping).build();
        session.sendMessage(new BinaryMessage(root.toByteArray()));
      } catch (IOException e) {
        stopHeartbeat();
      }
    }, HEART_BEAT_INTERVAL, HEART_BEAT_INTERVAL, TimeUnit.SECONDS);
  }

  public void stopHeartbeat() {
    if (scheduledFuture != null && !scheduledFuture.isCancelled()) {
      scheduledFuture.cancel(true);
    }
  }
}
