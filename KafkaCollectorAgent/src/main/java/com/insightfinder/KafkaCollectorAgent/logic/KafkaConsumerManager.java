package com.insightfinder.KafkaCollectorAgent.logic;

import com.insightfinder.KafkaCollectorAgent.logic.config.KafkaConfig;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.config.KafkaListenerEndpoint;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.kafka.support.TopicPartitionOffset;
import org.springframework.kafka.support.converter.MessageConverter;
import javax.annotation.PostConstruct;
import java.util.Arrays;
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

@EnableKafka
@Configuration
public class KafkaConsumerManager {
    public static class IFKafkaListenerEndpoint implements KafkaListenerEndpoint{
        private String topic;
        private String groupId;
        private Integer concurrency;

        public IFKafkaListenerEndpoint(String topic, String groupId, Integer concurrency) {
            this.topic = topic;
            this.groupId = groupId;
            this.concurrency = concurrency;
        }
        @Override
        public Collection<String> getTopics() {
            return Arrays.asList(topic);
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

    @Autowired
    private KafkaConfig kafkaConfig;
    @Autowired
    private GenericApplicationContext applicationContext;
    @Autowired
    private IFStreamingBufferManager ifStreamingBufferManager;

    public KafkaConsumerManager() {

    }

    @PostConstruct
    public void init(){
        int clusterNum = kafkaConfig.getBootstrapAddress().size();
        for (int i = 0; i < clusterNum; i++){
            ConsumerFactory consumerFactory = consumerFactory(kafkaConfig.getBootstrapAddress().get(i), kafkaConfig.getGroupId().get(i));
            ConcurrentKafkaListenerContainerFactory<String, String> factory = new ConcurrentKafkaListenerContainerFactory<>();
            factory.setBatchListener(false);
            factory.setConsumerFactory(consumerFactory);
            IFKafkaListenerEndpoint ifKafkaListenerEndpoint = new IFKafkaListenerEndpoint(kafkaConfig.getTopic().get(i), kafkaConfig.getGroupId().get(i), kafkaConfig.getConcurrency().get(i));
            ConcurrentMessageListenerContainer<String, String> container = factory.createListenerContainer(ifKafkaListenerEndpoint);
            container.setupMessageListener((MessageListener<Integer, String>) record -> {
                ifStreamingBufferManager.parseString(record.value().toString(), System.currentTimeMillis());
            });
            applicationContext.registerBeanDefinition("ConcurrentMessageListenerContainer" + i, BeanDefinitionBuilder.genericBeanDefinition(ConcurrentMessageListenerContainer.class,()->{return container;}).getBeanDefinition());
        }
    }

    public ConsumerFactory<String, String> consumerFactory(String bootstrapAddress, String groupId) {
        Map<String, Object> props = new HashMap<>();
        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                bootstrapAddress);
        props.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                groupId);
        props.put(
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        return new DefaultKafkaConsumerFactory<>(props);
    }

}
