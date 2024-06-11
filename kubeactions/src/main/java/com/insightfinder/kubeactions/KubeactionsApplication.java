package com.insightfinder.kubeactions;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KubeactionsApplication implements CommandLineRunner {

  public static void main(String[] args) {
    SpringApplication.run(KubeactionsApplication.class, args);
  }

  @Override
  public void run(String... args) throws Exception {
  }
}
