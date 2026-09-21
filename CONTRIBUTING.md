# Contributing

Contributions are welcome when they preserve the project's private LAN-party
scope and do not weaken its data-safety guarantees.

## Before submitting a change

1. Start from the current default branch and use a focused feature branch.
2. Do not commit real participant names, account identifiers, library exports,
   databases, credentials, tokens, logs, or screenshots containing such data.
3. Add focused tests for behavioural changes.
4. Run backend tests, frontend build, Steam-helper syntax check, dependency
   audits, and license inventory generation described in
   `docs/open-source-compliance.md`.
5. Update user, operator, privacy, and provider documentation when behaviour or
   collected data changes.

## Provenance

Contributors must have the right to submit their work and preserve notices for
code informed by third-party projects. Commits should use the Developer
Certificate of Origin convention:

```text
Signed-off-by: Name <email@example.org>
```

Add the line with `git commit --signoff`. Do not copy code from a project with
an incompatible or unknown license. Record material references and exact
revisions in `THIRD_PARTY_NOTICES.md`.

## Provider integrations

New integrations must document whether an API is official, which credentials
are processed, whether they are stored, how access is revoked, and which
provider terms apply. Unofficial integrations must remain optional and must
not be represented as endorsed by the provider.
