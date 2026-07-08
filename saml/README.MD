# InsightFinder SAML Relay Service

## Overview

InsightFinder supports SAML 2.0 SSO via a dedicated relay service (this app). It acts as the
SAML **Service Provider (SP)**, sitting between an Identity Provider (Teleport, Microsoft Entra
ID, Okta, etc.) and the InsightFinder backend:

```
Browser <-> IdP (Teleport / Entra ID / ...) <-> SAML Relay (this service) <-> InsightFinder backend
```

Flow (SP-initiated):
1. User enters their email on the InsightFinder login page and clicks the SAML button.
2. The backend matches the email domain against `saml.json` and redirects the browser to
   `https://<relay-host>/saml2/authenticate/<idp-name>`.
3. The relay builds a signed SAML `AuthnRequest` and redirects to the IdP's SSO URL.
4. The IdP authenticates the user and POSTs a SAML assertion back to the relay's ACS endpoint:
   `https://<relay-host>/login/saml2/sso/<idp-name>`.
5. The relay validates the assertion, extracts `email`/`firstname`/`lastname` from the
   configured attribute keys, and calls `POST {serverUrl}/api/v1/saml-user-verify`.
6. The backend JIT-provisions the user if needed and returns a one-time `state` token.
7. The relay redirects the browser to `{serverUrl}/ui/login-uie?state=<uuid>`, where the
   InsightFinder frontend exchanges the state for a session.

The relay also supports **IdP-initiated** SSO (e.g. clicking the app tile directly in Teleport's
dashboard) — Spring Security accepts unsolicited assertions at the same ACS endpoint by default.

`<idp-name>` is whatever key you choose under `saml.idp.<idp-name>` in configuration — it does
not need to be literally `teleport`, even when the IdP is Teleport.

## Prerequisites

- Java SDK 17+
- OpenSSL 1.0.2+ (for generating the SP key/cert)
- Network access from the relay to the IdP and to the InsightFinder backend
- A dedicated public hostname/domain for the relay (e.g. `saml.insightfinder.com`)

## Configuration reference (`application.yml`)

| Key | Description | Example |
|---|---|---|
| `server.port` | Port the relay listens on | `8080` |
| `insight-finder.serverUrl` | URL of the InsightFinder backend | `https://app.insightfinder.com` |
| `insight-finder.samlUrl` | Public URL of this relay service | `https://saml.insightfinder.com` |
| `insight-finder.sp-key` | Path to the SP's private key (generated below) | `/app/certs/sp.key` |
| `insight-finder.sp-cert` | Path to the SP's certificate (generated below) | `/app/certs/sp.crt` |
| `saml.idp.<name>.entity-id` | IdP's entity ID / metadata URL | `https://xxx.teleport.sh/enterprise/saml-idp/metadata` |
| `saml.idp.<name>.singlesignon-url` | IdP's SSO endpoint (optional if derivable from metadata) | `https://xxx.teleport.sh/enterprise/saml-idp/sso` |
| `saml.idp.<name>.idp-cert` | Path to the IdP's X.509 certificate | `/app/certs/idp/<name>.pem` |
| `saml.idp.<name>.email-key` | SAML attribute name containing the user's email | `email` |
| `saml.idp.<name>.firstname-key` | SAML attribute name containing the first name | `firstname` |
| `saml.idp.<name>.lastname-key` | SAML attribute name containing the last name | `lastname` |

Generate the SP key/cert once (regenerated automatically on every container start by
`entrypoint.sh`, so treat it as ephemeral, not something to hand out for the IdP to pin):
```bash
openssl req -newkey rsa:2048 -nodes -keyout sp.key -x509 -days 365 -out sp.crt
```

### Endpoints this service exposes

| Purpose | URL |
|---|---|
| SP metadata | `https://<relay-host>/saml2/service-provider-metadata/<idp-name>` |
| ACS (assertion consumer) | `https://<relay-host>/login/saml2/sso/<idp-name>` |
| Login-init (SP-initiated) | `https://<relay-host>/saml2/authenticate/<idp-name>` |

## Setting up an IdP: Teleport

1. In Teleport, go to **Resources → Enroll New Resource → SAML Application**.
2. Configure the Service Provider using the **manual entity ID / ACS URL fields**, not an
   uploaded SP metadata file — the relay regenerates its own SP signing cert on every restart,
   so pinning it via uploaded metadata will go stale:
   - **Entity ID**: `https://<relay-host>/saml2/service-provider-metadata/<idp-name>`
   - **ACS URL**: `https://<relay-host>/login/saml2/sso/<idp-name>`
3. Add attribute mappings (Format: `unspecified`):

   | Attribute Name | Attribute Value |
   |---|---|
   | `email` | `user.spec.traits.email` |
   | `firstname` | `user.spec.traits.firstname` |
   | `lastname` | `user.spec.traits.lastname` |

4. Make sure the Teleport users who should get SSO access actually have these traits set
   (`email`, `firstname`, `lastname`) — traits are per-user, not automatic.
5. From the app's detail page in Teleport, grab the **Entity ID** (IdP metadata URL), **SSO
   URL**, and **X.509 Certificate** — these feed into `saml.idp.<idp-name>` above.
6. Confirm the role(s) assigned to your users don't restrict `app_labels` in a way that would
   block access to this application.

Other IdPs (Entra ID, Okta, etc.) follow the same shape: give the IdP the relay's entity ID and
ACS URL, map `email`/`firstname`/`lastname`-equivalent claims, and bring back the IdP's SSO URL
and signing certificate.

## Registering the email domain with the InsightFinder backend

The relay only handles the SAML exchange — the *backend* decides which emails get routed to
which relay/IdP, via a `saml.json` file:

```json
{
  "@yourcompany.com": "https://<relay-host>/saml2/authenticate/<idp-name>"
}
```

This file lives at `WEB-INF/classes/saml.json` in the InsightFinder backend's webapp
(`CheckSamlLoginServlet` reads it on every email-domain check).

## Deploying via the InsightFinder Helm chart (`helm-charts/charts/insightfinder`)

The chart deploys the relay as its own pod (`saml.enabled: true`), and also mounts a
generated `saml.json` into the **main InsightFinder webapp pods** — enabling `saml.enabled`
affects both, since they share one toggle.

```yaml
saml:
  enabled: true
  image: docker.io/insightfinderinc/saml:latest
  idp:
    <idp-name>:
      samlEmail: "@yourcompany.com"
      entityid: https://<tenant>.teleport.sh/enterprise/saml-idp/metadata
      singlesignonurl: https://<tenant>.teleport.sh/enterprise/saml-idp/sso
      emailkey: email
      firstnamekey: firstname
      lastnamekey: lastname
      idp_cert: "<base64-encoded PEM certificate from the IdP>"
  ingress:
    ingressClassName: nginx
    hosts:
      - saml.insightfinder.com
    tls:
      enabled: true
      secretName: ingress-tls
```

Notes:
- All `saml.idp.*` entries are served by the **same relay process** at different
  `/saml2/authenticate/<idp-name>` paths — `saml.ingress.hosts` is shared across all of them,
  it is not per-IdP.
- The `saml.json` URL for every IdP entry is built from `first .Values.saml.ingress.hosts` —
  make sure `hosts` is populated (a list), not left relying on a separate singular `host` key.
- If the main app's own routing (Gateway API `HTTPRoute`, or a plain `Ingress` if
  `ingress.enabled: true`) doesn't already have a rule for the path the relay redirects to after
  login (`/ui/login-uie` as of this version), the final redirect back into InsightFinder will
  404. Check `templates/httproute.yaml` covers whatever path `SamlV2View.home()` redirects to.

## Testing

1. Confirm the relay is reachable and serving metadata:
   ```bash
   curl -sk https://<relay-host>/saml2/service-provider-metadata/<idp-name>
   ```
   Should return SP metadata XML.
2. From the InsightFinder login page, enter an email matching a domain in `saml.json` and
   confirm you're redirected to the IdP, then back into InsightFinder logged in.
3. Test IdP-initiated login too, if supported by your IdP (e.g. clicking the app tile directly
   in Teleport's dashboard) — should work without ever visiting the InsightFinder login page.

## Troubleshooting

- **Redirected to a broken/relative URL after entering email** — check the rendered
  `saml.json` inside the relay/webapp ConfigMap; a missing or empty host in the Helm values
  will produce a URL with no scheme/host.
- **Login succeeds at the IdP but errors out on redirect back** — check
  `kubectl logs deploy/<release>-saml`. The relay logs the full SAML principal attribute map on
  every login (`Principal attributes: {...}`), which shows exactly what the IdP sent — useful for
  fixing `email-key`/`firstname-key`/`lastname-key` mismatches.
- **404 after a successful login** — the relay's post-login redirect target isn't covered by
  the main app's routing config (see the Helm deployment notes above).
- **Stale config after a Helm/ConfigMap change** — Spring Boot reads `application.yml` once at
  startup; updating the ConfigMap alone does not make a running pod pick up the change. Restart
  the deployment (`kubectl rollout restart deployment/<release>-saml`).
