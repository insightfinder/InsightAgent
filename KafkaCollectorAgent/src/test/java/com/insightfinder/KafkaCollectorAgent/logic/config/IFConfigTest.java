package com.insightfinder.KafkaCollectorAgent.logic.config;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
@EnableConfigurationProperties(value = IFConfig.class)
@TestPropertySource(locations = "/config.properties")
class IFConfigTest {
    @Autowired
    private IFConfig ifConfig;

    @Test
    void testIFConfig(){
        assertThat(ifConfig.getUserName()).isEqualTo("username");
        assertThat(ifConfig.getServerUrl()).isEqualTo("https://stg.insightfinder.com");
        assertThat(ifConfig.getServerUri()).isEqualTo("/api/v1/customprojectrawdata");
        assertThat(ifConfig.getCheckAndCreateUri()).isEqualTo("/api/v1/check-and-add-custom-project");
        assertThat(ifConfig.getLicenseKey()).isEqualTo("key");
        assertThat(ifConfig.getSamplingIntervalInSeconds()).isEqualTo(300);
        assertThat(ifConfig.getProjectKey()).isEqualTo("project");
        assertThat(ifConfig.getInstanceKey()).isEqualTo("instance");
        assertThat(ifConfig.getTimestampKey()).isEqualTo("timestamp");
        assertThat(ifConfig.getMetricKey()).isEqualTo("metric");
        assertThat(ifConfig.getValueKey()).isEqualTo("value");
        assertThat(ifConfig.getProjectList()).isEqualTo(
            "{"
                + "'dataset_id:326CE741-4E1F-404F-BDA2-0D0D48AE4039,item_id': {'project': 'LogBenchmark1','system': 'LogBenchmarkSys1'},"
                + "'dataset_name:CrashEvent': {'project': 'LogBenchmark2','system': 'LogBenchmarkSys2'},"
                + "'item_id:item_123': {'project': 'LogBenchmark3','system': 'LogBenchmarkSys3'}"
                + "}"
        );
        assertThat(ifConfig.getInstanceList()).isEqualTo(new HashSet<>(Arrays.asList("100", "200")));
        assertThat(ifConfig.getMetricRegex()).isEqualTo(".m*");
        assertThat(ifConfig.getDataFormat()).isEqualTo("String");
        assertThat(ifConfig.getDataFormatRegex()).isEqualTo("^cd\\.\\|(?<project>\\w+)\\|\\.\\w+\\.\\w+\\.\\w+\\.(?<instance>\\w+\\-\\w+).(?<metric>.*) (?<value>[-\\d\\.]+) (?<timestamp>\\d+)");
        assertThat(ifConfig.getAgentType()).isEqualTo("Streaming");
        assertThat(ifConfig.getProjectDelimiter()).isEqualTo("\\|");
        assertThat(ifConfig.isLogParsingInfo()).isTrue();
        assertThat(ifConfig.isLogSendingData()).isTrue();
        assertThat(ifConfig.getKeystoreFile()).isEqualTo("keystoreFile");
        assertThat(ifConfig.getKeystorePassword()).isEqualTo("keystorePassword");
        assertThat(ifConfig.getTruststoreFile()).isEqualTo("truststoreFile");
        assertThat(ifConfig.getTruststorePassword()).isEqualTo("truststorePassword");
        assertThat(ifConfig.getBufferingTime()).isEqualTo(30);
        assertThat(ifConfig.getLogMetadataBufferingTime()).isEqualTo(300);
        assertThat(ifConfig.getMetricNameFilter()).isEqualTo("memory.memory.free");
        assertThat(ifConfig.getKafkaMetricLogInterval()).isEqualTo(3600);
        assertThat(ifConfig.isFastRecovery()).isTrue();
        assertThat(ifConfig.isLogProject()).isTrue();
        assertThat(ifConfig.getLogProjectName()).isEqualTo("projectName");
        assertThat(ifConfig.getLogSystemName()).isEqualTo("systemName");
        assertThat(ifConfig.getLogTimestampFormat()).isEqualTo("yyyy-MM-dd'T'HH:mm:ss");
        assertThat(ifConfig.getLogTimestampFieldPathList()).isEqualTo(
            Collections.singletonList("item_time"));
        assertThat(ifConfig.getLogComponentFieldPathList()).isEqualTo(new ArrayList<>(Arrays.asList("device_info.device_brand&device_info.device_modeltype", "device_info.device_name")));
        assertThat(ifConfig.getLogInstanceFieldPathList()).isEqualTo(Collections.singletonList("device_context_id"));
        assertThat(ifConfig.getLogMetadataTopics()).isEqualTo(new HashSet<>(Arrays.asList("metadata", "metadata1")));
        List<List<String>> componentList = new ArrayList<>();
        componentList.add(Arrays.asList("device_info.device_brand", "device_info.device_modeltype"));
        componentList.add(Collections.singletonList("device_info.device_name"));
        assertThat(ifConfig.getLogComponentList()).isEqualTo(componentList);
    }
}