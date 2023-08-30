package com.insightfinder.KafkaCollectorAgent.logic;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.HashSet;
import java.util.Set;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class IFProjectManagerTest {
    @Mock
    WebClient webClient;

    @Mock
    WebClient.RequestBodyUriSpec requestBodyUriSpec;

    @Mock
    WebClient.RequestHeadersSpec requestHeadersSpec;

    @Mock
    WebClient.RequestBodySpec requestBodySpec;

    @Mock
    WebClient.ResponseSpec responseSpec;
    @Mock
    private Mono<String> mono;
    @Mock
    private IFConfig ifConfig;
    @Mock
    private IFProjectManager ifProjectManager2;
    @InjectMocks
    private IFProjectManager ifProjectManager;

    @Test
    public void test(){
        MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
        bodyValues.add("userName", "userName");
        bodyValues.add("licenseKey", "xxxx");
        bodyValues.add("projectName", "projectName");
        bodyValues.add("operation", "check");
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        when(requestHeadersSpec.header(any(), any())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        when(mono.block()).thenReturn("{'isProjectExist': true}");
        when(ifConfig.getUserName()).thenReturn("userName");
        when(ifConfig.getLicenseKey()).thenReturn("licenseXXXX");

        boolean bSuc = ifProjectManager.checkProject("projectName", "systemName");
        assert(bSuc == true);
    }

    @Test
    public void test2(){
        MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
        bodyValues.add("userName", "userName");
        bodyValues.add("licenseKey", "xxxx");
        bodyValues.add("projectName", "projectName");
        bodyValues.add("operation", "check");
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        when(requestHeadersSpec.header(any(), any())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        when(mono.block()).thenReturn("{'success': true}");
        when(ifConfig.getUserName()).thenReturn("userName");
        when(ifConfig.getLicenseKey()).thenReturn("licenseXXXX");
        when(ifConfig.getSamplingIntervalInSeconds()).thenReturn(300);

        boolean bSuc = ifProjectManager.createProject("projectName", "systemName", "Metric");
        assert(bSuc == true);
    }

    @Test
    public void test2Fail(){
        MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
        bodyValues.add("userName", "userName");
        bodyValues.add("licenseKey", "xxxx");
        bodyValues.add("projectName", "projectName");
        bodyValues.add("operation", "check");
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        when(requestHeadersSpec.header(any(), any())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        when(mono.block()).thenReturn("{'success': false}");
        when(ifConfig.getUserName()).thenReturn("userName");
        when(ifConfig.getLicenseKey()).thenReturn("licenseXXXX");
        when(ifConfig.getSamplingIntervalInSeconds()).thenReturn(300);

        boolean bSuc = ifProjectManager.createProject("projectName", "systemName", "Metric");
        assert(bSuc == false);
    }


    @Test
    public void test3(){
        MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
        bodyValues.add("userName", "userName");
        bodyValues.add("licenseKey", "xxxx");
        bodyValues.add("projectName", "projectName");
        bodyValues.add("operation", "check");
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        when(requestHeadersSpec.header(any(), any())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        when(mono.block()).thenReturn("{'success': true}");
        when(ifConfig.getUserName()).thenReturn("userName");
        when(ifConfig.getLicenseKey()).thenReturn("licenseXXXX");
        when(ifConfig.getSamplingIntervalInSeconds()).thenReturn(300);

        Set<String> projects = new HashSet<>();
        projects.add("p1");
        ifProjectManager.setProjects(projects);
        ifProjectManager.getProjects().add("p3");
        boolean isSuc = ifProjectManager.checkAndCreateProject("p1", "s1", "Metric");
        assert(isSuc == true);
        isSuc = ifProjectManager.checkAndCreateProject("p2", "s1", "Metric");
        assert(isSuc == true);
    }
}