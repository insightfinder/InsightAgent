package com.insightfinder.util.Utils;

import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class Utils {
    @Bean
    public RestTemplate getRestTemplate(){
        return new RestTemplate();
    }
}
