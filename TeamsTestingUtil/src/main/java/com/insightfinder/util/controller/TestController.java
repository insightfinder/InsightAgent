package com.insightfinder.util.controller;


import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.util.config.Config;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.*;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.io.IOException;
import java.net.*;
import java.util.*;

@RestController
public class TestController {
    @Autowired
    private Config config;
    @Autowired
    private RestTemplate restTemplate;

    @GetMapping(path = "/start")
    public ResponseEntity<Void> testEnv(@RequestHeader(name = "host", required = true) final String host){
        return ResponseEntity.status(HttpStatus.FOUND).location(URI.create(step1(host))).build();
    }

    @PostMapping(path = "/test")
    public String testEnv2(@RequestParam(name = "code")final String code, @RequestHeader(name = "host", required = true)final String host) throws IOException {
        StringBuilder stringBuilder = new StringBuilder();
        if (code == null){
            stringBuilder.append("Step 1: failed, can not get authorization from tenant: " + config.getTenantId());
            return stringBuilder.toString();
        }else {
            stringBuilder.append("Step 1: success, can get authorization from tenant: " + config.getTenantId());
        }
        stringBuilder.append("\n");
        try {
            String msHost = "login.microsoftonline.com";
            if (pingHost(msHost, 80, 5000)){
                stringBuilder.append("Step 2: success, "+ msHost +" is reachable");
            }else {
                stringBuilder.append("Step 2: failed, "+ msHost +" is not reachable, please check your network: ping " + msHost +" in terminal!");
                return stringBuilder.toString();
            }
        }catch (Exception e){
            stringBuilder.append("Step 2: failed, " + e.getMessage());
            return stringBuilder.toString();
        }
        stringBuilder.append("\n");
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        String tokenUrl = String.format("https://login.microsoftonline.com/%s/oauth2/v2.0/token", config.getTenantId());
        MultiValueMap<String, String> requestMap = new LinkedMultiValueMap<>();
        requestMap.add("tenant", config.getTenantId());
        requestMap.add("client_id", config.getClientId());
        requestMap.add("scope", "offline_access https://graph.microsoft.com/ChannelMessage.Send https://graph.microsoft.com/offline_access");
        requestMap.add("client_secret", config.getClientCredentials());
        requestMap.add("code", code);
        requestMap.add("grant_type", "authorization_code");
        requestMap.add("redirect_uri", "http://"+host+"/test");
        try {
            HttpEntity<MultiValueMap<String, String>> entity = new HttpEntity<>(requestMap, headers);
            ResponseEntity<String> responseEntityStr = restTemplate.postForEntity(tokenUrl, entity, String.class);
            if (responseEntityStr.getStatusCode().is2xxSuccessful()){
                JsonObject jsonObject = new Gson().fromJson(responseEntityStr.getBody(), JsonObject.class);
                if (jsonObject.has("access_token")){
                    stringBuilder.append("Step 3: Success to get token, " + "Your teams integration env is Great!");
                }
            }
        }catch (Exception e){
            stringBuilder.append("Step 3: failed to get token, " + e.getMessage());
        }
        return stringBuilder.toString();
    }

    private String step1(String host){
        String url = String.format("https://login.microsoftonline.com/%s/oauth2/authorize?client_id=%s&response_type=code&redirect_uri=%s&response_mode=form_post&state=%s&resource=https://graph.microsoft.com"
                                    ,config.getTenantId(), config.getClientId(), "http://"+host + "/test", UUID.randomUUID().toString());
        return url;
    }

    public static boolean pingHost(String host, int port, int timeout) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), timeout);
            return true;
        } catch (IOException e) {
            return false; // Either timeout or unreachable or failed DNS lookup.
        }
    }
}
