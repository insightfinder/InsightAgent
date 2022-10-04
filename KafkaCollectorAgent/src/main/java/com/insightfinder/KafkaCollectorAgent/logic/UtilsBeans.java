package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.Gson;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Component
public class UtilsBeans {
    @Autowired
    private IFConfig ifConfig;

    @Bean
    public Gson getGson(){
        return new Gson();
    }

    @Bean
    public StreamingBuffers getStreamingBuffers(){
        return new StreamingBuffers(ifConfig.getBufferSize());
    }

    @Bean
    public WebClient getWebClient(){

        return WebClient.builder()
                .baseUrl(ifConfig.getServerUrl())
                .clientConnector(new ReactorClientHttpConnector(HttpClient.newConnection().compress(true).wiretap(true)))
                .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(20 * 1024 * 1024))
                .build();
    }
}
