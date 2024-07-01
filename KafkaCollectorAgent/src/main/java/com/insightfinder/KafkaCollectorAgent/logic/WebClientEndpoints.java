package com.insightfinder.KafkaCollectorAgent.logic;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.Logger;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
@RequiredArgsConstructor
public class WebClientEndpoints {
  @Autowired private final IFProjectManager projectManager;
  @Autowired private final IFConfig ifConfig;
  @Autowired private final WebClient webClient;
  private static final Logger logger = Logger.getLogger(WebClientEndpoints.class.getName());

  public void sendMetadataToIF(String data, String ifProjectName, String ifSystemName) {
    String dataType = ifConfig.isLogProject() ? "Log" : "Metric";
    if (projectManager.checkAndCreateProject(ifProjectName, ifSystemName, dataType)) {
      UUID uuid = UUID.randomUUID();
      MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
      bodyValues.add("licenseKey", ifConfig.getLicenseKey());
      bodyValues.add("projectName", ifProjectName);
      bodyValues.add("userName", ifConfig.getUserName());
      bodyValues.add("data", data);
      bodyValues.add("agentType", ifConfig.getAgentType());
      int dataSize = data.getBytes(StandardCharsets.UTF_8).length / 1024;
      webClient.post()
          .uri("/api/v1/agent-upload-instancemetadata")
          .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
          .body(BodyInserters.fromFormData(bodyValues))
          .retrieve()
          .bodyToMono(String.class)
          .timeout(Duration.ofMillis(100000))
          .onErrorResume(throwable -> Mono.just("RETRY"))
          .subscribe(res -> logger.log(Level.INFO,
              "sending metadata: request id: " + uuid + " data size: " + dataSize + " kb code: "
                  + res));
    }
  }

  public void sendDataToIF(String data, String ifProjectName, String ifSystemName) {
    String dataType = ifConfig.isLogProject() ? "Log" : "Metric";
    if (projectManager.checkAndCreateProject(ifProjectName, ifSystemName, dataType)) {
      UUID uuid = UUID.randomUUID();
      MultiValueMap<String, String> bodyValues = new LinkedMultiValueMap<>();
      bodyValues.add("licenseKey", ifConfig.getLicenseKey());
      bodyValues.add("projectName", ifProjectName);
      bodyValues.add("userName", ifConfig.getUserName());
      bodyValues.add("metricData", data);
      bodyValues.add("agentType", ifConfig.getAgentType());
      int dataSize = data.getBytes(StandardCharsets.UTF_8).length / 1024;
      webClient.post()
          .uri("/api/v1/customprojectrawdata")
          .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
          .body(BodyInserters.fromFormData(bodyValues))
          .retrieve()
          .bodyToMono(String.class)
          .timeout(Duration.ofMillis(100000))
          .onErrorResume(throwable -> Mono.just("RETRY"))
          .subscribe(res -> logger.log(Level.INFO,
              "sending data: request id: " + uuid + " data size: " + dataSize + " kb code: "
                  + res));
    }
  }
}
