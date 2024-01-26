package com.insightfinder.kubeactions.util;

import com.google.gson.Gson;
import org.mapdb.DB;
import org.mapdb.DBMaker;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import java.util.logging.Logger;

@Component
public class Utils {
    private final Logger logger = Logger.getLogger(Utils.class.getName());

    @Bean
    public Gson getGson() {
        return new Gson();
    }

    @Bean
    public RestTemplate getRestTemplate(){
        return new RestTemplate();
    }

    @Bean
    public DB getMapDB(){
        DB db = DBMaker.memoryDB().make();
        return db;
    }
}
