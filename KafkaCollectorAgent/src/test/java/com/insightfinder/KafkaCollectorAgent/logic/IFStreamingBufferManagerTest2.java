package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.Gson;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;
import org.springframework.util.ResourceUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.time.Duration;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
@SpringBootTest
@TestPropertySource(locations = "/config-metric.properties")
class IFStreamingBufferManagerTest2 {
    @Mock
    private IFProjectManager ifProjectManager;
    @MockBean
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
    private Mono<String> mono2;
    @Autowired
    private Gson gson;
    @Autowired
    private IFConfig ifConfig;
    @InjectMocks
    private IFStreamingBufferManager ifStreamingBufferManager;
    @Test
    public void test1() throws InvocationTargetException, NoSuchMethodException, IllegalAccessException, IOException {
        ifStreamingBufferManager.setIfConfig(ifConfig);
        ifStreamingBufferManager.setGson(gson);
        ifStreamingBufferManager.setProjectList(ifStreamingBufferManager.getProjectMapping(ifConfig.getProjectList()));
        ifStreamingBufferManager.init();
        ifStreamingBufferManager.parseString("metric", "cs.|100|.ea.prod.lin.server-1.metric_group.metric_subgroup.metric_1 10 10000", 10000L);
        ifStreamingBufferManager.parseString("metric", "cs.|100|.ea.prod.lin.server-2.metric_group.metric_subgroup.metric_1 10 10000", 10000L);
        ifStreamingBufferManager.parseString("metric", "cs.|300|.ea.prod.lin.server-2.metric_group.metric_subgroup.metric_1 10 10000", 10000L);
        ifStreamingBufferManager.parseString("metric", "cs.|100|.ea.prod.lin.server-1.metric_group.metric_subgroup.etric_1 10 10000", 10000L);

    }

}