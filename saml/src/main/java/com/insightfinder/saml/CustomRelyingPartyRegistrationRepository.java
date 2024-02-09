package com.insightfinder.saml;

import java.io.InputStream;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.ArrayList;
import java.util.List;
import org.apache.commons.codec.binary.Base64;
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

  public static final String FFX_URL = "https://login.microsoftonline.com/9edc902a-24c0-475e-8e0d-7fd62eb788a9/federationmetadata/2007-06/federationmetadata.xml?appid=c8ca165a-c83e-46e9-a198-e98f228258df";
  private final List<RelyingPartyRegistration> registrations = new ArrayList<>();

  public CustomRelyingPartyRegistrationRepository() throws Exception {
    addDefaultRegistrations();
  }

  private void addDefaultRegistrations() throws Exception {
    RelyingPartyRegistration ffxRegistration = RelyingPartyRegistrations.fromMetadataLocation(
        FFX_URL).registrationId("fairfaxcounty").build();
    RelyingPartyRegistration ifRegistration = RelyingPartyRegistrations.fromMetadataLocation(
        FFX_URL).registrationId("insightfinder").build();
    RelyingPartyRegistration dellRegistration = createDellRelyingPartyRegistration();
    add(ffxRegistration);
    add(ifRegistration);
    add(dellRegistration);
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


  public RelyingPartyRegistration createDellRelyingPartyRegistration() throws Exception {
    X509Certificate verificationCertificate = loadCertificate("Teleport-SAML-IDP-X509.pem");
    Saml2X509Credential verificationCredential = new Saml2X509Credential(
        verificationCertificate, Saml2X509Credential.Saml2X509CredentialType.VERIFICATION);

    X509Certificate spCertificate = loadCertificate("local.crt");
    PrivateKey spPrivateKey = loadPrivateKey("local.key");
    Saml2X509Credential signingCredential = new Saml2X509Credential(
        spPrivateKey, spCertificate, Saml2X509Credential.Saml2X509CredentialType.SIGNING);

    return RelyingPartyRegistration.withRegistrationId("dell")
        .assertingPartyDetails(details -> details
            .entityId(
                "https://elayif.teleport.sh/enterprise/saml-idp/metadata") // The IdP's Entity ID
            .singleSignOnServiceLocation(
                "https://elayif.teleport.sh/enterprise/saml-idp/sso") // The IdP's SSO URL
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