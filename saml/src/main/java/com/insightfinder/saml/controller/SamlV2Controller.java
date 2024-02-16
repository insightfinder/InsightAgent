package com.insightfinder.saml.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController("/saml")
public class SamlV2Controller {

  @Autowired
  private RelyingPartyRegistrationRepository relyingPartyRegistrationRepository;

  @GetMapping("/registrations/{name}")
  public String getAllRegistrations(@PathVariable String name) {
    return name;
  }
}
