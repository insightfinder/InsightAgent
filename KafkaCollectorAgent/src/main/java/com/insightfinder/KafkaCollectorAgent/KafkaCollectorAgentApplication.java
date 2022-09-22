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
	@Autowired
	private IFStreamingBufferManager ifStreamingBufferManager;

	@Bean
	CommandLineRunner getCommandLineRunner(ApplicationContext ctx){
		return (ars)->{
			for (Thread t : ThreadUtils.getAllThreads()) {
				if (t.getName().startsWith("ConcurrentMessageListenerContainer")){
					ifStreamingBufferManager.addThreadBuffer(t.getId());
				}
			}
		};
	}

	public static void main(String[] args) {
		SpringApplication app = new SpringApplication(KafkaCollectorAgentApplication.class);
		app.setWebApplicationType(WebApplicationType.NONE);
		app.run(args);
	}

}
