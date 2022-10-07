package com.insightfinder.KafkaCollectorAgent.logic;

import com.google.gson.Gson;
import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Component;
import org.springframework.util.ResourceUtils;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.TrustManagerFactory;
import java.io.FileInputStream;
import java.security.KeyStore;
import java.util.logging.Level;
import java.util.logging.Logger;

@Component
public class UtilsBeans {
    private Logger logger = Logger.getLogger(UtilsBeans.class.getName());

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

    private SslContext createSSLContext() {
        try {
            SslContextBuilder sslContextBuilder = SslContextBuilder.forClient();
            boolean loadKeys = false;
            if (ifConfig.getKeystoreFile() != null && ifConfig.getKeystorePassword() != null){
                logger.log(Level.INFO, "key store file: "+ ifConfig.getKeystoreFile());
                logger.log(Level.INFO, "key store password: "+ ifConfig.getKeystorePassword());
                logger.log(Level.INFO, "key store type <keystore.type>: "+ KeyStore.getDefaultType());
                logger.log(Level.INFO, "key store algorithm <ssl.KeyManagerFactory.algorithm>: "+ KeyManagerFactory.getDefaultAlgorithm());
                loadKeys = true;
                KeyStore keyStore = KeyStore.getInstance(KeyStore.getDefaultType());
                keyStore.load(new FileInputStream(ResourceUtils.getFile(ifConfig.getKeystoreFile())), ifConfig.getKeystorePassword().toCharArray());
                KeyManagerFactory keyManagerFactory = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
                keyManagerFactory.init(keyStore, ifConfig.getKeystorePassword().toCharArray());
                sslContextBuilder = sslContextBuilder.keyManager(keyManagerFactory);
            }

            if (ifConfig.getTruststoreFile() != null && ifConfig.getTruststorePassword() != null){
                logger.log(Level.INFO, "trust store file: "+ ifConfig.getTruststoreFile());
                logger.log(Level.INFO, "trust store password: "+ ifConfig.getTruststorePassword());
                logger.log(Level.INFO, "trust store type <keystore.type>: "+ KeyStore.getDefaultType());
                logger.log(Level.INFO, "trust store algorithm <ssl.KeyManagerFactory.algorithm>: "+ KeyManagerFactory.getDefaultAlgorithm());
                loadKeys = true;
                KeyStore trustStore = KeyStore.getInstance(KeyStore.getDefaultType());
                trustStore.load(new FileInputStream((ResourceUtils.getFile(ifConfig.getTruststoreFile()))), ifConfig.getTruststorePassword().toCharArray());
                TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
                trustManagerFactory.init(trustStore);
                sslContextBuilder = sslContextBuilder.trustManager(trustManagerFactory);
            }
            if (loadKeys){
                return sslContextBuilder.build();
            }else {
                return null;
            }

        }
        catch (Exception e) {
            throw new RuntimeException("Error creating SSL context.");
        }
    }

    @Bean
    public WebClient getWebClient(){
        HttpClient client = HttpClient.create().compress(true).wiretap(true);
        SslContext sslContext = createSSLContext();
        if (sslContext!= null){
            client = client.secure(spec -> spec.sslContext(sslContext));
        }
        ClientHttpConnector connector = new ReactorClientHttpConnector(client);
        return WebClient.builder()
                .baseUrl(ifConfig.getServerUrl())
                .clientConnector(connector)
                .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(20 * 1024 * 1024))
                .build();
    }
}
