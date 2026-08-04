package com.insightfinder.saml;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.insightfinder.saml.SamlProperties.IdpConfig;
import com.insightfinder.saml.config.IFConfig;
import java.security.PrivateKey;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.saml2.provider.service.registration.AssertingPartyMetadata;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Unit tests covering the code changed on II-24323 when migrating from Spring Boot 2.7 /
 * Spring Security 5.7 to Spring Boot 3.5 / Spring Security 6.5. The migration rewrote the
 * teleport {@link RelyingPartyRegistration} builder to use the new
 * {@code Saml2X509Credential.verification(..)}/{@code signing(..)} factories and the
 * {@code assertingPartyMetadata(..)} / {@code verificationX509Credentials(..)} /
 * {@code signingX509Credentials(..)} API, so these tests assert the resulting registration
 * is wired the same way it was before the migration.
 */
class CustomRelyingPartyRegistrationRepositoryTest {

  private static final String IDP = "teleport";

  private CustomRelyingPartyRegistrationRepository repository;
  private SamlProperties samlProperties;
  private IFConfig ifConfig;

  @BeforeEach
  void setUp() throws Exception {
    repository = new CustomRelyingPartyRegistrationRepository();
    samlProperties = new SamlProperties();
    ifConfig = new IFConfig();
    ifConfig.setSpCert(resourcePath("certs/sp-cert.pem"));
    ifConfig.setSpKey(resourcePath("certs/sp-key.pem"));
    ReflectionTestUtils.setField(repository, "samlProperties", samlProperties);
    ReflectionTestUtils.setField(repository, "ifConfig", ifConfig);
  }

  private static String resourcePath(String name) throws Exception {
    return new ClassPathResource(name).getFile().getAbsolutePath();
  }

  private IdpConfig teleportIdpConfig() throws Exception {
    IdpConfig idpConfig = new IdpConfig();
    idpConfig.setEntityId("https://teleport.example.com/metadata");
    idpConfig.setSinglesignonUrl("https://teleport.example.com/sso");
    idpConfig.setIdpCert(resourcePath("certs/idp-cert.pem"));
    return idpConfig;
  }

  @Test
  void loadPrivateKeyParsesPkcs8Key() throws Exception {
    PrivateKey key = repository.loadPrivateKey(resourcePath("certs/sp-key.pem"));

    assertEquals("RSA", key.getAlgorithm());
    assertEquals("PKCS#8", key.getFormat());
  }

  @Test
  void findByRegistrationIdReturnsAddedRegistration() throws Exception {
    RelyingPartyRegistration registration =
        repository.createTeleportRelyingPartyRegistration(IDP, teleportIdpConfig());
    repository.add(registration);

    assertSame(registration, repository.findByRegistrationId(IDP));
  }

  @Test
  void findByRegistrationIdReturnsNullWhenAbsent() {
    assertNull(repository.findByRegistrationId("does-not-exist"));
  }

  @Test
  void createTeleportRegistrationCopiesIdpConfig() throws Exception {
    RelyingPartyRegistration registration =
        repository.createTeleportRelyingPartyRegistration(IDP, teleportIdpConfig());

    assertEquals(IDP, registration.getRegistrationId());

    AssertingPartyMetadata idp = registration.getAssertingPartyMetadata();
    assertEquals("https://teleport.example.com/metadata", idp.getEntityId());
    assertEquals("https://teleport.example.com/sso", idp.getSingleSignOnServiceLocation());
    assertEquals(Saml2MessageBinding.REDIRECT, idp.getSingleSignOnServiceBinding());
    assertTrue(idp.getWantAuthnRequestsSigned());
  }

  @Test
  void createTeleportRegistrationSetsSigningAndVerificationCredentials() throws Exception {
    RelyingPartyRegistration registration =
        repository.createTeleportRelyingPartyRegistration(IDP, teleportIdpConfig());

    assertFalse(registration.getSigningX509Credentials().isEmpty(),
        "SP signing credential (from spKey/spCert) must be present");
    assertFalse(registration.getAssertingPartyMetadata().getVerificationX509Credentials().isEmpty(),
        "IdP verification credential (from idpCert) must be present");
  }
}
