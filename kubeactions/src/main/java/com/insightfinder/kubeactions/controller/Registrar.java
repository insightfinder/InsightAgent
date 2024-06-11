package com.insightfinder.kubeactions.controller;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.kubeactions.config.IFConfig;
import java.util.Map;
import javax.annotation.PostConstruct;
import org.jetbrains.annotations.NotNull;
import org.mapdb.DB;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

@Component
public class Registrar {
    private static final Logger log = LoggerFactory.getLogger(Registrar.class);

    @Autowired
    private DB mapDB;
    @Autowired
    private Gson gson;
    @Autowired
    private IFConfig ifConfig;
    @Autowired
    private RestTemplate restTemplate;

    @PostConstruct
    void init(){
        String url  = String.format("%s/api/v2/IFK8SActionServerServlet", ifConfig.getServerUrl());
        log.info(url);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        HttpEntity<MultiValueMap<String, String>> request = getMultiValueMapHttpEntity(headers);
        ResponseEntity<String> response = restTemplate.postForEntity(url, request , String.class);
        if (response.getStatusCode().is2xxSuccessful()){
            JsonObject resObj = gson.fromJson(response.getBody(), JsonObject.class);
            System.out.println(resObj);
            Map map = mapDB.hashMap("map").createOrOpen();
            map.put("serverId", "26185b8f-cfe9-45ef-a640-57e3baa3bea5");
            mapDB.commit();
        }
    }

    @NotNull
    private HttpEntity<MultiValueMap<String, String>> getMultiValueMapHttpEntity(HttpHeaders headers) {
        MultiValueMap<String, String> map= new LinkedMultiValueMap<>();
        map.add("userName", ifConfig.getUserName());
        map.add("licenseKey", ifConfig.getLicense());
        map.add("system", ifConfig.getSystem());
        map.add("serverIp", ifConfig.getActionServerIp());
        map.add("serverPort", ifConfig.getActionServerPort());
        HttpEntity<MultiValueMap<String, String>> request = new HttpEntity<>(map, headers);
        return request;
    }
}
