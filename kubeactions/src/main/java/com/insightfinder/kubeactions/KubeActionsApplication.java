package com.insightfinder.kubeactions;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KubeActionsApplication implements CommandLineRunner {

  public static void main(String[] args) {
    SpringApplication.run(KubeActionsApplication.class, args);
  }

  @Override
  public void run(String... args) throws Exception {
  }
}
