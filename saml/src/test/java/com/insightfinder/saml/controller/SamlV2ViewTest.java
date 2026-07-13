package com.insightfinder.saml.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.google.gson.Gson;
import com.insightfinder.saml.SamlProperties;
import com.insightfinder.saml.SamlProperties.IdpConfig;
import com.insightfinder.saml.config.IFConfig;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpEntity;
import org.springframework.http.ResponseEntity;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.view.RedirectView;

/**
 * Unit tests for {@link SamlV2View}, covering the II-24323 change that replaced the
 * {@code org.apache.http.util.TextUtils.isEmpty(..)} name-key check with Spring's
 * {@code StringUtils.hasLength(..)}. The behaviour under test is the first-/last-name
 * defaulting ("John"/"Doe" when the IdP config has no name key) and the resulting redirect.
 */
@ExtendWith(MockitoExtension.class)
class SamlV2ViewTest {

  private static final String REGISTRATION_ID = "teleport";
  private static final String SERVER_URL = "https://app.insightfinder.com";

  @Mock
  private Saml2AuthenticatedPrincipal principal;
  @Mock
  private RestTemplate restTemplate;

  private SamlV2View view;
  private SamlProperties samlProperties;
  private IdpConfig idpConfig;

  @BeforeEach
  void setUp() {
    view = new SamlV2View();
    IFConfig ifConfig = new IFConfig();
    ifConfig.setServerUrl(SERVER_URL);

    idpConfig = new IdpConfig();
    idpConfig.setEmailKey("email");

    samlProperties = new SamlProperties();
    Map<String, IdpConfig> idpMap = new HashMap<>();
    idpMap.put(REGISTRATION_ID, idpConfig);
    samlProperties.setIdp(idpMap);

    ReflectionTestUtils.setField(view, "gson", new Gson());
    ReflectionTestUtils.setField(view, "restTemplate", restTemplate);
    ReflectionTestUtils.setField(view, "ifConfig", ifConfig);
    ReflectionTestUtils.setField(view, "samlProperties", samlProperties);

    lenient().when(principal.getRelyingPartyRegistrationId()).thenReturn(REGISTRATION_ID);
    lenient().when(principal.getFirstAttribute("email")).thenReturn("user@corp.com");
  }

  @SuppressWarnings("unchecked")
  private MultiValueMap<String, String> captureVerifyRequestBody() {
    ArgumentCaptor<HttpEntity<?>> captor = ArgumentCaptor.forClass(HttpEntity.class);
    verify(restTemplate).postForEntity(anyString(), captor.capture(), eq(String.class));
    return (MultiValueMap<String, String>) captor.getValue().getBody();
  }

  private void stubVerifyResponse(String body) {
    when(restTemplate.postForEntity(anyString(), any(), eq(String.class)))
        .thenReturn(ResponseEntity.ok(body));
  }

  @Test
  void usesJohnDoeDefaultsWhenNameKeysAreAbsent() {
    // firstnameKey / lastnameKey left null -> StringUtils.hasLength(null) == false -> defaults
    stubVerifyResponse("{\"state\":\"tok123\"}");

    RedirectView result = view.home(principal, null);

    MultiValueMap<String, String> body = captureVerifyRequestBody();
    assertEquals("John", body.getFirst("firstName"));
    assertEquals("Doe", body.getFirst("lastName"));
    assertEquals("user@corp.com", body.getFirst("email"));
    assertEquals(SERVER_URL + "/ui/login-uie?state=tok123", result.getUrl());
  }

  @Test
  void usesPrincipalAttributesWhenNameKeysArePresent() {
    idpConfig.setFirstnameKey("fn");
    idpConfig.setLastnameKey("ln");
    when(principal.getFirstAttribute("fn")).thenReturn("Alice");
    when(principal.getFirstAttribute("ln")).thenReturn("Smith");
    stubVerifyResponse("{\"state\":\"tok999\"}");

    RedirectView result = view.home(principal, null);

    MultiValueMap<String, String> body = captureVerifyRequestBody();
    assertEquals("Alice", body.getFirst("firstName"));
    assertEquals("Smith", body.getFirst("lastName"));
    assertEquals(SERVER_URL + "/ui/login-uie?state=tok999", result.getUrl());
  }

  @Test
  void redirectsToServerUrlWhenNoStateReturned() {
    stubVerifyResponse("{}");

    RedirectView result = view.home(principal, null);

    assertEquals(SERVER_URL, result.getUrl());
  }
}
