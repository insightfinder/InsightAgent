package com.insightfinder.KafkaCollectorAgent.logic;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import com.insightfinder.KafkaCollectorAgent.logic.config.KafkaConfig;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.boot.autoconfigure.kafka.DefaultKafkaConsumerFactoryCustomizer;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.config.KafkaListenerEndpoint;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.TopicPartitionOffset;
import org.springframework.kafka.support.converter.MessageConverter;

import javax.annotation.PostConstruct;
import java.util.*;
import java.util.regex.Pattern;

@EnableKafka
@Configuration
public class KafkaConsumerManager {
    @Autowired
    private KafkaConfig kafkaConfig;
    @Autowired
    private IFConfig ifConfig;
    @Autowired
    private GenericApplicationContext applicationContext;
    @Autowired
    private IFStreamingBufferManager ifStreamingBufferManager;
    @Autowired
    private ObjectProvider<DefaultKafkaConsumerFactoryCustomizer> customizers;

    public KafkaConsumerManager() {

    }

    public void setKafkaConfig(KafkaConfig kafkaConfig) {
        this.kafkaConfig = kafkaConfig;
    }

    public void setIfConfig(IFConfig ifConfig) {
        this.ifConfig = ifConfig;
    }

    @PostConstruct
    public void init() {
        Map<String, Map<String, String>> clusterInfo = kafkaConfig.getKafkaClusterInfo();
        int clusterIndex = 0;
        for (Map<String, String> cluster : clusterInfo.values()) {
            ConsumerFactory<String, String> consumerFactory = consumerFactory(cluster);
            customizers.orderedStream().forEach(customizer -> customizer.customize((DefaultKafkaConsumerFactory<?, ?>) consumerFactory));
            ConcurrentKafkaListenerContainerFactory<String, String> factory = new ConcurrentKafkaListenerContainerFactory<>();
            factory.setBatchListener(true);
            factory.setConsumerFactory(consumerFactory);
            IFKafkaListenerEndpoint ifKafkaListenerEndpoint = new IFKafkaListenerEndpoint(cluster.get("topic"), cluster.get("group.id"), Integer.valueOf(cluster.get("concurrency")));
            ConcurrentMessageListenerContainer<String, String> container = factory.createListenerContainer(ifKafkaListenerEndpoint);
            if (ifConfig.isFastRecovery()) {
                container.setupMessageListener(new IFMessageListener(ifStreamingBufferManager));
            } else {
                container.setupMessageListener((MessageListener<Integer, String>) record -> {
                    ifStreamingBufferManager.parseString(record.topic(), record.value(), System.currentTimeMillis());
                });
            }
            applicationContext.registerBeanDefinition("ConcurrentMessageListenerContainer" + clusterIndex, BeanDefinitionBuilder.genericBeanDefinition(ConcurrentMessageListenerContainer.class, () -> {
                return container;
            }).getBeanDefinition());
            clusterIndex++;
        }
    }

    public ConsumerFactory<String, String> consumerFactory(Map<String, String> cluster) {
        Map<String, Object> props = new HashMap<>();
        for (Map.Entry entry : cluster.entrySet()) {
            props.put(entry.getKey().toString(), entry.getValue());
        }
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        return new DefaultKafkaConsumerFactory<>(props);
    }

    public static class IFMessageListener implements MessageListener<Integer, String>, ConsumerSeekAware {
        private final IFStreamingBufferManager ifStreamingBufferManager;

        public IFMessageListener(IFStreamingBufferManager ifStreamingBufferManager) {
            this.ifStreamingBufferManager = ifStreamingBufferManager;
        }

        @Override
        public void onMessage(ConsumerRecord<Integer, String> data) {
            ifStreamingBufferManager.parseString(data.topic() ,data.value(), System.currentTimeMillis());
        }

        @Override
        public void onMessage(ConsumerRecord<Integer, String> data, Acknowledgment acknowledgment) {
            MessageListener.super.onMessage(data, acknowledgment);
        }

        @Override
        public void onMessage(ConsumerRecord<Integer, String> data, Consumer<?, ?> consumer) {
            MessageListener.super.onMessage(data, consumer);
        }

        @Override
        public void onMessage(ConsumerRecord<Integer, String> data, Acknowledgment acknowledgment, Consumer<?, ?> consumer) {
            MessageListener.super.onMessage(data, acknowledgment, consumer);
        }

        @Override
        public void registerSeekCallback(ConsumerSeekCallback callback) {
            ConsumerSeekAware.super.registerSeekCallback(callback);
        }

        @Override
        public void onPartitionsAssigned(Map<TopicPartition, Long> assignments, ConsumerSeekCallback callback) {
            assignments.forEach((topic, action) -> callback.seekToEnd(topic.topic(), topic.partition()));
        }

        @Override
        public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
            ConsumerSeekAware.super.onPartitionsRevoked(partitions);
        }

        @Override
        public void onIdleContainer(Map<TopicPartition, Long> assignments, ConsumerSeekCallback callback) {
            ConsumerSeekAware.super.onIdleContainer(assignments, callback);
        }

        @Override
        public void onFirstPoll() {
            ConsumerSeekAware.super.onFirstPoll();
        }

        @Override
        public void unregisterSeekCallback() {
            ConsumerSeekAware.super.unregisterSeekCallback();
        }
    }

    public static class IFKafkaListenerEndpoint implements KafkaListenerEndpoint {
        private final String topic;
        private final String groupId;
        private final Integer concurrency;

        public IFKafkaListenerEndpoint(String topic, String groupId, Integer concurrency) {
            this.topic = topic;
            this.groupId = groupId;
            this.concurrency = concurrency;
        }

        @Override
        public Collection<String> getTopics() {
            return Collections.singletonList(topic);
        }

        @Override
        public String getGroupId() {
            return groupId;
        }

        @Override
        public Integer getConcurrency() {
            return concurrency;
        }

        @Override
        public String getId() {
            return "";
        }

        @Override
        public String getGroup() {
            return "";
        }

        @Override
        public TopicPartitionOffset[] getTopicPartitionsToAssign() {
            return new TopicPartitionOffset[0];
        }

        @Override
        public Pattern getTopicPattern() {
            return null;
        }

        @Override
        public String getClientIdPrefix() {
            return null;
        }

        @Override
        public Boolean getAutoStartup() {
            return null;
        }

        @Override
        public void setupListenerContainer(MessageListenerContainer listenerContainer, MessageConverter messageConverter) {

        }

        @Override
        public boolean isSplitIterables() {
            return true;
        }

    }
}
