# Security Policy

## Supported versions

Security fixes are provided for the latest tagged release only. Operators
should deploy a pinned tag, keep the reverse proxy and containers updated, and
review the release notes before upgrading.

## Reporting a vulnerability

Do not publish credentials, tokens, database extracts, or exploitable details
in a public issue. Contact the repository owner through a private channel on
the hosting platform. If no private channel is available, open a minimal issue
requesting private contact without disclosing technical details.

Include the affected version, impact, reproduction conditions, and any known
mitigation. Please allow a reasonable period for investigation before public
disclosure.

## Security model

This application is intended for a small, trusted group. It is not a public
multi-tenant service.

- TLS and HTTP Basic Auth at the reverse proxy are the access-control boundary.
- The selected participant in the browser is not a verified user identity.
- The in-app admin password only unlocks administration views. It is not an
  authorization mechanism for individual REST endpoints.
- Every admitted user can modify shared application data.
- Provider tokens are stored locally in the `provider-auth` volume. Backups of
  that volume are secrets and must be encrypted and access-controlled.
- Direct integrations marked experimental use unofficial provider interfaces.

Do not expose backend, frontend, PostgreSQL, or the Steam helper directly to
the Internet. Use `compose.production.yml`, bind application containers to
loopback, and place the documented authenticated TLS proxy in front of them.

## Deployment requirements

- Generate unique Basic Auth, admin, and PostgreSQL passwords.
- Never publish `.env`, database backups, imported libraries, access logs, or
  provider-auth files.
- Keep unofficial provider integrations disabled unless their risks are
  understood and accepted by the operator and account owner.
- Apply upload and archive limits appropriate to the host's available memory
  and disk space.
- Rotate provider sessions and passwords after any suspected token exposure.
