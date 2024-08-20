package com.insightfinder.kubeactions.client.websocket.handler;

import com.insightfinder.InsightFinderAgent.proto.IfAgentInstructionWrapper.HPAAction;
import com.insightfinder.InsightFinderAgent.proto.IfAgentInstructionWrapper.IfAgentInstruction;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class K8sInstructionHandler {

  @Autowired
  private HPAActionHandler hpaActionHandler;

  public void handlerK8sInstruction(IfAgentInstruction instruction) {
    if (instruction.hasHPAAction()) {
      HPAAction hpaAction = instruction.getHPAAction();
      hpaActionHandler.handleHpaAction(hpaAction);
    }
  }
}
