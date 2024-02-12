package com.insightfinder.saml;

import java.util.HashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "saml")
public class SamlProperties {

  private Map<String, IdpConfig> idp = new HashMap<>();

  public static class IdpConfig {
    private String entityId;
    private String singlesignonUrl;

    public String getEntityId() {
      return entityId;
    }

    public void setEntityId(String entityId) {
      this.entityId = entityId;
    }

    public String getSinglesignonUrl() {
      return singlesignonUrl;
    }

    public void setSinglesignonUrl(String singlesignonUrl) {
      this.singlesignonUrl = singlesignonUrl;
    }
  }

  public void setIdp(Map<String, IdpConfig> idp) {
    this.idp = idp;
  }

  public Map<String, IdpConfig> getIdp() {
    return idp;
  }
}