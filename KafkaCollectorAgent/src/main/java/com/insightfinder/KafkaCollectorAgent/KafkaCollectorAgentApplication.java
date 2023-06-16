package com.insightfinder.KafkaCollectorAgent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KafkaCollectorAgentApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(KafkaCollectorAgentApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }

}
