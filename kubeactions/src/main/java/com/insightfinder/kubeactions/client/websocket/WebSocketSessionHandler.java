package com.insightfinder.kubeactions.client.websocket;

import com.insightfinder.InsightFinderAgent.proto.IfAgentInstructionWrapper.IfAgentInstruction;
import com.insightfinder.kubeactions.client.websocket.handler.K8sInstructionHandler;
import com.insightfinder.kubeactions.client.websocket.handler.WebSocketConnectionCloseHandler;
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

@Component
public class WebSocketSessionHandler implements WebSocketHandler {

  private static final Logger log = LoggerFactory.getLogger(WebSocketSessionHandler.class);

  @Autowired
  private K8sInstructionHandler k8sInstructionHandler;
  @Autowired
  private WebSocketConnectionCloseHandler webSocketConnectionCloseHandler;

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
    if (message instanceof TextMessage textMessage) {
      System.out.println(textMessage.getPayload());
    } else if (message instanceof BinaryMessage binaryMessage) {
      IfAgentInstruction ifAgentInstruction = IfAgentInstruction.parseFrom(
          binaryMessage.getPayload());
      k8sInstructionHandler.handlerK8sInstruction(ifAgentInstruction);
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
  }

  /**
   * Called when WS is closed.
   */
  @Override
  public void afterConnectionClosed(WebSocketSession session, CloseStatus closeStatus)
      throws Exception {
    log.info("WebSocket connection closed, closeStatus: " + closeStatus.getReason());
  }

  @Override
  public boolean supportsPartialMessages() {
    // TODO Auto-generated method stub
    return false;
  }

}
