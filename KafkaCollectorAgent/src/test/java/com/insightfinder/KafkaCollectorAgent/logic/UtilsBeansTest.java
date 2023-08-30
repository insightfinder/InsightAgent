package com.insightfinder.KafkaCollectorAgent.logic;

import com.insightfinder.KafkaCollectorAgent.logic.config.IFConfig;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.Mockito;
import org.mockito.internal.matchers.Any;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.util.ResourceUtils;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.security.KeyStore;
import java.security.NoSuchAlgorithmException;
import java.security.cert.CertificateException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class UtilsBeansTest {
    @Mock
    private IFConfig ifConfig;
    @Mock
    private KeyStore keyStore;
    @Mock
    private File file;
    @InjectMocks
    private UtilsBeans utilsBeans;

    @Test
    public void test() throws InstantiationException, IllegalAccessException, CertificateException, IOException, NoSuchAlgorithmException {
        when(ifConfig.getKeystoreFile()).thenReturn("classpath:client.jks");
        when(ifConfig.getKeystorePassword()).thenReturn("123456");
        when(ifConfig.getTruststoreFile()).thenReturn("classpath:clienttrust.jks");
        when(ifConfig.getTruststorePassword()).thenReturn("123456");
        when(ifConfig.getServerUrl()).thenReturn("url");
        utilsBeans.getWebClient();
    }

}