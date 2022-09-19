package com.insightfinder.KafkaCollectorAgent.logic.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
@ConfigurationProperties(prefix = "kafka")
public class KafkaConfig {

    private List<String> bootstrapAddress;
    private List<String> groupId;
    private List<String> topic;
    private List<Integer> concurrency;

    public KafkaConfig() {
    }

    public List<String> getBootstrapAddress() {
        return bootstrapAddress;
    }

    public void setBootstrapAddress(List<String> bootstrapAddress) {
        this.bootstrapAddress = bootstrapAddress;
    }

    public List<String> getGroupId() {
        return groupId;
    }

    public void setGroupId(List<String> groupId) {
        this.groupId = groupId;
    }

    public List<String> getTopic() {
        return topic;
    }

    public void setTopic(List<String> topic) {
        this.topic = topic;
    }

    public List<Integer> getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(List<Integer> concurrency) {
        this.concurrency = concurrency;
    }
}
