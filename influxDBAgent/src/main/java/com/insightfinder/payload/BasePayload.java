package com.insightfinder.payload;

import com.insightfinder.utilities.GsonUtility;
import java.io.Serializable;


public abstract class BasePayload implements Serializable {

  protected String projectName;
  protected String projectType;
  protected String userName;
  protected String instanceName;
  protected String systemName;

  public BasePayload() {

  }

  public BasePayload(String userName, String systemName) {
    this.userName = userName;
    this.systemName = systemName;
  }

  public BasePayload(String projectName, String userName, String instanceName) {
    this.projectName = projectName;
    this.userName = userName;
    this.instanceName = instanceName;
  }

  public BasePayload(String projectName, String projectType, String userName, String instanceName) {
    this.projectName = projectName;
    this.projectType = projectType;
    this.userName = userName;
    this.instanceName = instanceName;
  }

  public String getProjectName() {
    return projectName;
  }

  public void setProjectName(String projectName) {
    this.projectName = projectName;
  }

  public String getUserName() {
    return userName;
  }

  public void setUserName(String userName) {
    this.userName = userName;
  }

  public String getInstanceName() {
    return instanceName;
  }

  public void setInstanceName(String instanceName) {
    this.instanceName = instanceName;
  }

  public String getProjectType() {
    return projectType;
  }

  public void setProjectType(String projectType) {
    this.projectType = projectType;
  }

  public String getSystemName() {
    return systemName;
  }

  public void setSystemName(String systemName) {
    this.systemName = systemName;
  }


  public String toJson() {
    return GsonUtility.gson.toJson(this);
  }

  @Override
  public String toString() {
    return toJson();
  }

  @Override
  public int hashCode() {
    final int prime = 31;
    int result = 1;
    result = prime * result + ((instanceName == null) ? 0 : instanceName.hashCode());
    result = prime * result + ((projectName == null) ? 0 : projectName.hashCode());
    result = prime * result + ((projectType == null) ? 0 : projectType.hashCode());
    result = prime * result + ((userName == null) ? 0 : userName.hashCode());
    return result;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) {
      return true;
    }
    if (obj == null) {
      return false;
    }
    if (getClass() != obj.getClass()) {
      return false;
    }
    BasePayload other = (BasePayload) obj;
    if (instanceName == null) {
      if (other.instanceName != null) {
        return false;
      }
    } else if (!instanceName.equals(other.instanceName)) {
      return false;
    }
    if (projectName == null) {
      if (other.projectName != null) {
        return false;
      }
    } else if (!projectName.equals(other.projectName)) {
      return false;
    }
    if (projectType == null) {
      if (other.projectType != null) {
        return false;
      }
    } else if (!projectType.equals(other.projectType)) {
      return false;
    }
    if (userName == null) {
      return other.userName == null;
    } else {
      return userName.equals(other.userName);
    }
  }
}