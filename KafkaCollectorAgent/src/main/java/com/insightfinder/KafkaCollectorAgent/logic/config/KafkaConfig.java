package com.insightfinder.KafkaCollectorAgent.logic.config;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.AbstractEnvironment;
import org.springframework.core.env.EnumerablePropertySource;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.stream.StreamSupport;

@Component
public class KafkaConfig {
    @Autowired
    private Environment env;

    private int clusterNum;

    public KafkaConfig() {
    }

    public Map<String, Map<String, String>> getKafkaClusterInfo() {
        Map<String, Map<String, String>> info = new HashMap<>();
        MutablePropertySources propSrcs = ((AbstractEnvironment) env).getPropertySources();
        StreamSupport.stream(propSrcs.spliterator(), false)
                .filter(ps -> ps instanceof EnumerablePropertySource)
                .map(ps -> ((EnumerablePropertySource) ps).getPropertyNames())
                .flatMap(Arrays::stream)
                .forEach(propName -> {
                    if (propName.startsWith("kafka")) {
                        String[] splitPropNames = propName.split("\\.", 2);
                        if (!info.containsKey(splitPropNames[0])) {
                            info.put(splitPropNames[0], new HashMap<>());
                        }
                        info.get(splitPropNames[0]).put(splitPropNames[1], env.getProperty(propName));
                    }
                });
        return info;
    }

    public int getClusterNum() {
        return clusterNum;
    }

    public void setClusterNum(int clusterNum) {
        this.clusterNum = clusterNum;
    }
}
