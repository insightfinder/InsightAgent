package com.insightfinder.saml.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "insight-finder")
public class IFConfig {

  private String serverUrl;
  private String samlUrl;
  private String spKey;
  private String spCert;

  public IFConfig() {
  }

  public String getServerUrl() {
    return serverUrl;
  }

  public void setServerUrl(String serverUrl) {
    this.serverUrl = serverUrl;
  }

  public String getSamlUrl() {
    return samlUrl;
  }

  public void setSamlUrl(String samlUrl) {
    this.samlUrl = samlUrl;
  }

  public String getSpKey() {
    return spKey;
  }

  public void setSpKey(String spKey) {
    this.spKey = spKey;
  }

  public String getSpCert() {
    return spCert;
  }

  public void setSpCert(String spCert) {
    this.spCert = spCert;
  }
}
