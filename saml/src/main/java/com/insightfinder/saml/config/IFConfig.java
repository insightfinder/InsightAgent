package com.insightfinder.saml.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "insight-finder")
public class IFConfig {
    private String serverUrl;
    private String samlUrl;


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
}
