package com.insightfinder.saml;

import com.insightfinder.saml.SamlProperties.IdpConfig;
import com.insightfinder.saml.config.IFConfig;
import java.io.InputStream;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import javax.annotation.PostConstruct;
import org.apache.commons.codec.binary.Base64;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.saml2.credentials.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;
import org.springframework.stereotype.Service;

@Service
public class CustomRelyingPartyRegistrationRepository implements
    RelyingPartyRegistrationRepository {

  public static final String TELEPORT = "teleport";

  @Autowired
  private SamlProperties samlProperties;
  @Autowired
  private IFConfig ifConfig;
  private final List<RelyingPartyRegistration> registrations = new ArrayList<>();

  public CustomRelyingPartyRegistrationRepository() throws Exception {
  }

  @PostConstruct
  private void init() throws Exception {
    addDefaultRegistrations();
  }


  private void addDefaultRegistrations() throws Exception {
    Map<String, IdpConfig> idpMap = samlProperties.getIdp();
    for (String idp : idpMap.keySet()) {
      IdpConfig idpConfig = idpMap.get(idp);
      RelyingPartyRegistration registration;
      if (idpConfig.getEntityId().contains(TELEPORT)) {
        registration = createTeleportRelyingPartyRegistration(idp, idpConfig);
      } else {
        String entityId = idpConfig.getEntityId();
        registration = RelyingPartyRegistrations.fromMetadataLocation(
            entityId).registrationId(idp).build();
      }
      add(registration);
    }
  }

  @Override
  public RelyingPartyRegistration findByRegistrationId(String registrationId) {
    for (RelyingPartyRegistration registration : this.registrations) {
      if (registration.getRegistrationId().equals(registrationId)) {
        return registration;
      }
    }
    return null;
  }

  public void add(RelyingPartyRegistration newRegistration) {
    this.registrations.add(newRegistration);
  }


  public RelyingPartyRegistration createTeleportRelyingPartyRegistration(String idp,
      IdpConfig idpConfig)
      throws Exception {
    X509Certificate verificationCertificate = loadCertificate(idpConfig.getIdpCert());
    Saml2X509Credential verificationCredential = new Saml2X509Credential(
        verificationCertificate, Saml2X509Credential.Saml2X509CredentialType.VERIFICATION);

    X509Certificate spCertificate = loadCertificate(ifConfig.getSpCert());
    PrivateKey spPrivateKey = loadPrivateKey(ifConfig.getSpKey());
    Saml2X509Credential signingCredential = new Saml2X509Credential(
        spPrivateKey, spCertificate, Saml2X509Credential.Saml2X509CredentialType.SIGNING);

    return RelyingPartyRegistration.withRegistrationId(idp)
        .assertingPartyDetails(details -> details
            .entityId(
                idpConfig.getEntityId()) // The IdP's Entity ID
            .singleSignOnServiceLocation(
                idpConfig.getSinglesignonUrl()) // The IdP's SSO URL
            .singleSignOnServiceBinding(Saml2MessageBinding.REDIRECT) // The SSO binding
            .wantAuthnRequestsSigned(true)) // Indicates you want to sign requests
        .credentials(c -> {
          c.add(verificationCredential);
          c.add(signingCredential); // Add the signing credential here
        })
        .build();
  }

  public PrivateKey loadPrivateKey(String path) throws Exception {
    // Adjust this method to read the key from your preferred location
    InputStream inputStream = new ClassPathResource(path).getInputStream();
    String key = new String(inputStream.readAllBytes());

    // Remove the first and last lines
    String privateKeyPEM = key
        .replace("-----BEGIN PRIVATE KEY-----", "")
        .replaceAll(System.lineSeparator(), "")
        .replace("-----END PRIVATE KEY-----", "");

    // Base64 decode the data
    byte[] encoded = Base64.decodeBase64(privateKeyPEM);

    KeyFactory keyFactory = KeyFactory.getInstance("RSA");
    PKCS8EncodedKeySpec keySpec = new PKCS8EncodedKeySpec(encoded);
    return keyFactory.generatePrivate(keySpec);
  }

  private X509Certificate loadCertificate(String path) throws Exception {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    try (InputStream inputStream = new ClassPathResource(path).getInputStream()) {
      return (X509Certificate) factory.generateCertificate(inputStream);
    }
  }

}