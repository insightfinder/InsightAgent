package com.insightfinder.KafkaCollectorAgent.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.RequiredArgsConstructor;

@Data
@Builder
@RequiredArgsConstructor
@AllArgsConstructor
public class ProjectInfo {
  private String project;
  private String system;
}
