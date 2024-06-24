package com.insightfinder.KafkaCollectorAgent.model;

import java.util.Objects;

public class ProjectInfo {
  private String project;
  private String system;

  public ProjectInfo() {
  }

  public ProjectInfo(String project, String system) {
    this.project = project;
    this.system = system;
  }

  public String getProject() {
    return project;
  }

  public void setProject(String project) {
    this.project = project;
  }

  public String getSystem() {
    return system;
  }

  public void setSystem(String system) {
    this.system = system;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (o == null || getClass() != o.getClass()) {
      return false;
    }
    ProjectInfo that = (ProjectInfo) o;
    return Objects.equals(project, that.project) && Objects.equals(system,
        that.system);
  }

  @Override
  public int hashCode() {
    return Objects.hash(project, system);
  }
}
