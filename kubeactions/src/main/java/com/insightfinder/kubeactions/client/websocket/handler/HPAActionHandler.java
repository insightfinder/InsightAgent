package com.insightfinder.kubeactions.client.websocket.handler;

import com.insightfinder.InsightFinderAgent.proto.IfAgentInstructionWrapper.HPAAction;
import org.springframework.stereotype.Component;

@Component
public class HPAActionHandler {

  public void handleHpaAction(HPAAction hpaAction) {
    // TODO: handle HPA
    System.out.println(hpaAction);
  }
}
