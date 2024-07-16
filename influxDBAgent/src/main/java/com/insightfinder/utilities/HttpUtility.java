package com.insightfinder.utilities;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpUtility {

  public static HttpResponse<String> sendHttpRequest(String endpoint, String requestBody)
      throws IOException, InterruptedException {

    HttpClient client = HttpClient.newHttpClient();
    HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(endpoint))
        .POST(HttpRequest.BodyPublishers.ofString(requestBody))
        .build();

    return client.send(request,
        HttpResponse.BodyHandlers.ofString());
  }
}
