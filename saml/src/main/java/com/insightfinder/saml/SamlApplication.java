package com.insightfinder.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(SamlProperties.class)
public class SamlApplication {
	public static void main(String[] args) {
		SpringApplication.run(SamlApplication.class, args);
	}
}
