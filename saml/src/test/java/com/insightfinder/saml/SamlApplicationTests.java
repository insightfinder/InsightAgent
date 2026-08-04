package com.insightfinder.saml;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

// Override the deployment cert paths (which point at /app/certs/... only present in the
// container) with the throwaway certs under src/test/resources/certs so the full context
// can boot. The teleport entity-id from application.yml already contains "teleport", so the
// repository builds the registration locally instead of fetching remote metadata.
@SpringBootTest
@TestPropertySource(properties = {
    "insight-finder.sp-key=src/test/resources/certs/sp-key.pem",
    "insight-finder.sp-cert=src/test/resources/certs/sp-cert.pem",
    "saml.idp.teleport.idp-cert=src/test/resources/certs/idp-cert.pem"
})
class SamlApplicationTests {

	@Test
	void contextLoads() {
	}

}
