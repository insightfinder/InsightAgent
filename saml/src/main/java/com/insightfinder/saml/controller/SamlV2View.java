package com.insightfinder.saml.controller;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.saml.config.IFConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.view.RedirectView;

import java.util.Map;

@Controller
public class SamlV2View {
    @Autowired
    private Gson gson;
    @Autowired
    private RestTemplate restTemplate;
    @Autowired
    private IFConfig ifConfig;
    @Autowired
    private RelyingPartyRegistrationRepository relyingPartyRegistrationRepository;

    @RequestMapping("/")
    public RedirectView home(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal, Model model) {
        String email =  principal.getFirstAttribute("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress");
        String firstname = principal.getFirstAttribute("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname");
        String lastName = principal.getFirstAttribute("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname");
        String state = verify(email, firstname, lastName);
        return new RedirectView(ifConfig.getServerUrl() + "/auth/login2?state=" + state);
    }

    private String verify(String email, String firstName, String lastName){
        String url  = String.format("%s/api/v1/saml-user-verify", ifConfig.getServerUrl());
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        HttpEntity<MultiValueMap<String, String>> request = getMultiValueMapHttpEntity(headers, email, firstName, lastName);
        ResponseEntity<String> response = restTemplate.postForEntity(url, request , String.class);
        if (response.getStatusCode().is2xxSuccessful()){
            JsonObject resObj = gson.fromJson(response.getBody(), JsonObject.class);
            if (resObj.has("state")){
                return resObj.get("state").getAsString();
            }
        }
        return null;
    }

    private HttpEntity<MultiValueMap<String, String>> getMultiValueMapHttpEntity(HttpHeaders headers, String email, String firstName, String lastName) {
        MultiValueMap<String, String> map= new LinkedMultiValueMap<>();
        map.add("email", email);
        map.add("firstName", firstName);
        map.add("lastName", lastName);
        HttpEntity<MultiValueMap<String, String>> request = new HttpEntity<>(map, headers);
        return request;
    }



}