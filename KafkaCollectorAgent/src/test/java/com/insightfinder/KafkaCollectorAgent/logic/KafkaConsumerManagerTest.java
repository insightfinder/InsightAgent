package com.insightfinder.KafkaCollectorAgent.logic;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.config.KafkaConfig;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.kafka.DefaultKafkaConsumerFactoryCustomizer;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@TestPropertySource(locations = "/config.properties")
class KafkaConsumerManagerTest {
    @Autowired
    private IFConfig ifConfig;
    @Mock
    private GenericApplicationContext applicationContext;
    @MockBean
    private WebClient webClient;
    @Autowired
    private KafkaConfig kafkaConfig;
    @Mock
    private ObjectProvider<DefaultKafkaConsumerFactoryCustomizer> customizers;
    @InjectMocks
    private KafkaConsumerManager kafkaConsumerManager;
    @Test
    public void test(){
        kafkaConsumerManager.setKafkaConfig(kafkaConfig);
        kafkaConsumerManager.setIfConfig(ifConfig);
        kafkaConsumerManager.init();
    }

    @Test
    public void test2(){
        kafkaConsumerManager.setKafkaConfig(kafkaConfig);
        ifConfig.setFastRecovery(false);
        kafkaConsumerManager.setIfConfig(ifConfig);
        kafkaConsumerManager.init();
    }

}