package com.insightfinder.util;

import com.insightfinder.util.config.Config;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UtilApplication implements CommandLineRunner {
	public static void main(String[] args) {
		SpringApplication.run(UtilApplication.class, args);
	}

	@Override
	public void run(String... args) throws Exception {
	}

}
