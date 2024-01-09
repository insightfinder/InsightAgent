package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.common.hash.BloomFilter;
import com.google.common.hash.Funnels;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.apache.kafka.common.protocol.types.Field;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
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

import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
//@MockitoSettings(strictness = Strictness.LENIENT)
@SuppressWarnings("unchecked")
@SpringBootTest
@TestPropertySource(locations = "/config.properties")
class IFStreamingBufferManagerTest {
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
    @Spy
    private IFStreamingBufferManager ifStreamingBufferManager;
    @Test
    public void test1() throws InvocationTargetException, NoSuchMethodException, IllegalAccessException, IOException {
        ifStreamingBufferManager.setIfConfig(ifConfig);
        ifStreamingBufferManager.setGson(gson);
        ifStreamingBufferManager.setProjectList(ifStreamingBufferManager.getProjectMapping(ifConfig.getProjectList()));
        String content = new String(Files.readAllBytes(ResourceUtils.getFile("classpath:DeviceContext.json").getAbsoluteFile().toPath()));

        ifStreamingBufferManager.parseString("metadata", content, 10000L);
        String content2 = new String(Files.readAllBytes(ResourceUtils.getFile("classpath:CrashEvent_ItemEvent.json").getAbsoluteFile().toPath()));
        ifStreamingBufferManager.parseString("test1", content2, 10000L);
    }

    @Test
    public void test2(){
        String timestamp =  ifStreamingBufferManager.convertToMS("10000000000");
        assert(timestamp.length() > 10);
        String dateFormat = "yyyy-MM-dd'T'HH:mm:ssZZZZZ";
        String dateTime = "2023-02-24T07:22:23-05:00";
        long time =  ifStreamingBufferManager.getGMTinHourFromMillis(dateTime, dateFormat);
        assert(time > -1);
        String dateTime2 = "yyyy-MM-dd'T'HH:mm:ssZZZZZ";
        time =  ifStreamingBufferManager.getGMTinHourFromMillis(dateTime2, dateFormat);
        assert(time == -1);
        DateTimeFormatter rfc3339Formatter = DateTimeFormatter.ofPattern(dateFormat)
                .withResolverStyle(ResolverStyle.LENIENT);
        ZonedDateTime zonedDateTime = ifStreamingBufferManager.parseRfc3339(dateTime, rfc3339Formatter);
    }

    @Test
    public void test3(){
        when(ifProjectManager.checkAndCreateProject(anyString(), anyString(), anyString())).thenReturn(true);
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        lenient().when(requestHeadersSpec.header(anyString(), anyString())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        lenient().when(mono.timeout(any(Duration.class))).thenReturn(mono);
        when(mono.onErrorResume(any())).thenReturn(Mono.just("RETRY"));
        ifStreamingBufferManager.setIfConfig(ifConfig);
        ifStreamingBufferManager.sendMetadataToIF("data", "p1", "s1");
        ifStreamingBufferManager.sendToIF("data", "p1", "s1");
    }

    @Test
    public void test4(){
        when(ifProjectManager.checkAndCreateProject(anyString(), anyString(), anyString())).thenReturn(true);
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        lenient().when(requestHeadersSpec.header(any(), any())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        when(mono.timeout(any(Duration.class))).thenReturn(mono);
        when(mono.onErrorResume(any())).thenReturn(Mono.just("SUC"));
        ifStreamingBufferManager.setIfConfig(ifConfig);
        ifStreamingBufferManager.sendMetadataToIF("data", "p1", "s1");
        ifStreamingBufferManager.sendToIF("data", "p1", "s1");
        Map<Long, JsonObject> sortByTimestampMap = new HashMap<>();
        sortByTimestampMap.put(10000L, new JsonObject());
        ifStreamingBufferManager.sendToIF(sortByTimestampMap, "p1", "s1");
    }

    @Test
    public void test5(){
        IFStreamingBuffer ifStreamingBuffer = new IFStreamingBuffer("p1", "s1");
        ifStreamingBuffer.addData("i1", 10000L, "m1", 1.0);
        ifStreamingBuffer.addData("i1", 10000L, "m2", 1.0);
        ifStreamingBuffer.addData("i1", 1693423553000L, "m2", 1.0);
        ifStreamingBuffer.addData("i2", 10000L, "m1", 1.0);
        ifStreamingBuffer.addData("i2", 1693423553000L, "m2", 1.0);
        ifStreamingBuffer.addData("i2", 10001L, "m2", 1.0);
        ifStreamingBufferManager.setIfConfig(ifConfig);
        ifStreamingBufferManager.convertBackToOldFormat(ifStreamingBuffer.getAllInstanceDataMap(), "p1", "s1", 1);
        ifStreamingBufferManager.convertBackToOldFormat(ifStreamingBuffer.getAllInstanceDataMap(), "p1", "s1", 1);
        Map<String, IFStreamingBuffer> collectingDataMap = new HashMap<>();
        collectingDataMap.put("p1", ifStreamingBuffer);
        ifStreamingBufferManager.mergeDataAndSendToIF2(collectingDataMap);
        ifStreamingBufferManager.mergeDataAndSendToIF2(collectingDataMap);
    }

    @Test
    public void test6(){
        when(ifProjectManager.checkAndCreateProject(anyString(), anyString(), anyString())).thenReturn(true);
        when(webClient.post()).thenReturn(requestBodyUriSpec);
        when(requestBodyUriSpec.uri(anyString())).thenReturn(requestBodySpec);
        when(requestBodySpec.header(any(), any())).thenReturn(requestBodySpec);
        lenient().when(requestHeadersSpec.header(any(), any())).thenReturn(requestHeadersSpec);
        when(requestBodySpec.body(any())).thenReturn(requestHeadersSpec);
        when(requestHeadersSpec.retrieve()).thenReturn(responseSpec);
        when(responseSpec.bodyToMono(String.class)).thenReturn(mono);
        lenient().when(mono.timeout(any(Duration.class))).thenReturn(mono);
        when(mono.onErrorResume(any())).thenReturn(Mono.just("RETRY"));

        ifStreamingBufferManager.setGson(gson);
        ifStreamingBufferManager.setIfConfig(ifConfig);
        ifStreamingBufferManager.setProjectList(ifStreamingBufferManager.getProjectMapping(ifConfig.getProjectList()));
        Map<String, Set<JsonObject>> collectingDataMap = new HashMap<>();
        collectingDataMap.put("p1@s1", new HashSet<>(Arrays.asList(new JsonObject(), new JsonObject())));
        ifStreamingBufferManager.mergeLogDataAndSendToIF2(collectingDataMap);
        Map<String, Set<JsonObject>> collectingMetaDataMap = new HashMap<>();
        collectingMetaDataMap.put("LogBenchmark1", new HashSet<>(Arrays.asList(new JsonObject(), new JsonObject())));
        ifStreamingBufferManager.mergeLogMetaDataAndSendToIF2(collectingMetaDataMap);
    }
}