package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import javax.annotation.PostConstruct;
import java.util.HashSet;
import java.util.Set;
import java.util.logging.Logger;

@Component
public class IFProjectManager {
    private Logger logger = Logger.getLogger(IFProjectManager.class.getName());
    @Autowired
    private IFConfig ifConfig;
    @Autowired
    private Gson gson;
    @Autowired
    private WebClient webClient;
    private Set<String> projects;

    public IFProjectManager() {

    }

    @PostConstruct
    public void init() throws InterruptedException {
        projects = new HashSet<>();
    }

    boolean checkAndCreateProject(String projectName, String systemName){
        if (projects.contains(projectName)){
            return true;
        }
        if (checkProject(projectName, systemName)){
            projects.add(projectName);
        }else {
            if (createProject(projectName, systemName)){
                projects.add(projectName);
            }
        }
        return projects.contains(projectName);
    }

    boolean checkProject(String projectName, String systemName){
        MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
        bodyValues.add("userName", ifConfig.getUserName());
        bodyValues.add("licenseKey", ifConfig.getLicenseKey());
        bodyValues.add("projectName", projectName);
        bodyValues.add("operation", "check");
        String res = webClient.post()
                .uri("/api/v1/check-and-add-custom-project")
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body(BodyInserters.fromFormData(bodyValues))
                .retrieve()
                .bodyToMono(String.class)
                .block();
        JsonObject resObject = new Gson().fromJson(res, JsonObject.class);
        if (resObject.has("isProjectExist") && resObject.get("isProjectExist").getAsBoolean()){
            return true;
        }
        return false;
    }

    boolean createProject(String projectName, String systemName){
        MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
        bodyValues.add("userName", ifConfig.getUserName());
        bodyValues.add("licenseKey", ifConfig.getLicenseKey());
        bodyValues.add("projectName", projectName);
        bodyValues.add("operation", "create");
        bodyValues.add("instanceType", "PrivateCloud");
        bodyValues.add("projectCloudType", "PrivateCloud");
        bodyValues.add("samplingInterval", String.valueOf(ifConfig.getSamplingIntervalInSeconds()/60));
        bodyValues.add("samplingIntervalInSeconds", String.valueOf(ifConfig.getSamplingIntervalInSeconds()));
        bodyValues.add("systemName", systemName);
        bodyValues.add("dataType", "Metric");
        bodyValues.add("insightAgentType", ifConfig.getAgentType());
        String res = webClient.post()
                .uri("/api/v1/check-and-add-custom-project")
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body(BodyInserters.fromFormData(bodyValues))
                .retrieve()
                .bodyToMono(String.class)
                .block();
        JsonObject resObject = new Gson().fromJson(res, JsonObject.class);
        if (resObject.has("success")&&resObject.get("success").getAsBoolean()){
            return true;
        }
        return false;
    }


}
