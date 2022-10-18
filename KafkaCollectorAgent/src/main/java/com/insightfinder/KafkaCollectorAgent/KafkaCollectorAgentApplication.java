package com.insightfinder.KafkaCollectorAgent;

import com.insightfinder.KafkaCollectorAgent.logic.IFStreamingBufferManager;
import org.apache.commons.lang3.ThreadUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@SpringBootApplication
public class KafkaCollectorAgentApplication {
	public static void main(String[] args) {
		SpringApplication app = new SpringApplication(KafkaCollectorAgentApplication.class);
		app.setWebApplicationType(WebApplicationType.NONE);
		app.run(args);
	}

}
