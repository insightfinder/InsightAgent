package com.insightfinder.kubeactions.config;

import org.mapdb.DB;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.Map;

@Configuration
@ConfigurationProperties(prefix = "insight-finder")
public class IFConfig {
    @Autowired
    private DB mapDB;
    private String userName;
    private String license;
    private String system;
    private String actionServerIp;
    private String actionServerPort;
    private String actionServerId;
    private String actionServerName;
    private String serverUrl;

    public IFConfig() {
    }

    public String getUserName() {
        return userName;
    }

    public void setUserName(String userName) {
        this.userName = userName;
    }

    public String getLicense() {
        return license;
    }

    public void setLicense(String license) {
        this.license = license;
    }

    public String getSystem() {
        return system;
    }

    public void setSystem(String system) {
        this.system = system;
    }

    public String getActionServerIp() {
        return actionServerIp;
    }

    public void setActionServerIp(String actionServerIp) {
        this.actionServerIp = actionServerIp;
    }

    public String getActionServerPort() {
        return actionServerPort;
    }

    public void setActionServerPort(String actionServerPort) {
        this.actionServerPort = actionServerPort;
    }

    public String getActionServerId() {
        if (actionServerId == null || actionServerId.length() == 0){
            Map map = mapDB.hashMap("map").createOrOpen();
            if (map.containsKey("serverid")){
                actionServerId = map.get("serverid").toString();
            }
        }
        return actionServerId;
    }

    public void setActionServerId(String actionServerId) {
        this.actionServerId = actionServerId;
    }

    public String getServerUrl() {
        return serverUrl;
    }

    public void setServerUrl(String serverUrl) {
        this.serverUrl = serverUrl;
    }

    public String getActionServerName() {
        return actionServerName;
    }

    public void setActionServerName(String actionServerName) {
        this.actionServerName = actionServerName;
    }
}
