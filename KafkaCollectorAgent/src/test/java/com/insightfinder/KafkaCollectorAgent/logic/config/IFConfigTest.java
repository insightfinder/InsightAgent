package com.insightfinder.KafkaCollectorAgent.logic.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.*;
@SpringBootTest
@TestPropertySource(locations = "/config.properties")
class IFConfigTest {
    @Autowired
    private IFConfig ifConfig;
    @MockBean
    private WebClient webClient;

    @Test
    void testIFConfig(){
        if (ifConfig != null) {
            assert (ifConfig.isLogParsingInfo());
            assert (ifConfig.getUserName() != null);
            assert (ifConfig.getServerUri() != null);
            assert (ifConfig.getCheckAndCreateUri() != null);
            assert (ifConfig.getLicenseKey() != null);
            assert (ifConfig.getSamplingIntervalInSeconds() > 0);
            assert (ifConfig.getProjectDelimiter() != null);
            assert (ifConfig.getLogMetadataTopics() != null);
            assert (ifConfig.getInstanceKey() != null);
            assert (ifConfig.getTimestampKey() != null);
            assert (ifConfig.getAgentType() != null);
            assert (ifConfig.getProjectKey() != null);
            assert (ifConfig.isLogSendingData() );
            assert (ifConfig.isLogProject());
            assert (ifConfig.getLogTimestampFormat() != null);
            assert (ifConfig.getMetricNameFilter() != null);
            assert (ifConfig.getServerUrl() != null);
            assert (ifConfig.getMetricKey() != null);
            assert (ifConfig.getValueKey() != null);
            assert (ifConfig.getKeystoreFile() != null);
            assert (ifConfig.getTruststoreFile() != null);
            assert (ifConfig.getTruststorePassword() != null);
            assert (ifConfig.getKeystorePassword() != null);
        }
    }
}