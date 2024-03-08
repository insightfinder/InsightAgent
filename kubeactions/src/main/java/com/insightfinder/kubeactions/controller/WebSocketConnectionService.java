package com.insightfinder.kubeactions.controller;

import java.net.URI;
import javax.annotation.PostConstruct;
import org.springframework.stereotype.Service;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.WebSocketClient;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Service
public class WebSocketConnectionService extends TextWebSocketHandler {

  private WebSocketClient webSocketClient;

  @PostConstruct
  public void init() {
    this.webSocketClient = new StandardWebSocketClient();
    connect();
  }

  private void connect() {
    try {
      // Update to the actual WebSocket server URI
      String uri = "ws://localhost:9999";
      webSocketClient.doHandshake(this, new WebSocketHttpHeaders(), URI.create(uri)).get();
    } catch (Exception e) {
      e.printStackTrace();
    }
  }

  @Override
  public void afterConnectionEstablished(WebSocketSession session) {
    System.out.println("Connected to WebSocket server!");
    try {
      session.sendMessage(new TextMessage("Hello from client!"));
    } catch (Exception e) {
      e.printStackTrace();
    }
  }

  @Override
  protected void handleTextMessage(WebSocketSession session, TextMessage message) {
    System.out.println("Received: " + message.getPayload());
    // Handle incoming message here
  }

  @Override
  public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
    System.out.println("Connection closed: " + status);
  }
}
