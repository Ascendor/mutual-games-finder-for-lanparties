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

## Dependency updates

Backend dependency declarations live in `backend/pyproject.toml`; exact versions
and artifact hashes are recorded in `backend/uv.lock`. Keep the lockfile in sync
when changing the manifest. Transitive-only updates may change just the lockfile.
Both Docker targets use `uv sync --locked` and reject a stale lockfile. Test
packages belong in `[dependency-groups].test` and are only installed in the
`test` target. Run `docker compose run --build --rm backend-tests`; it starts
an isolated PostgreSQL test database without production credentials or volumes.
See `docs/open-source-compliance.md` for dependency updates using the pinned uv
tooling image. Refresh runtime license inventories and SBOMs after changes.

Dependabot groups monthly frontend minor and patch updates. Frontend major
versions are excluded from automatic version updates and require a separate
migration with a Docker build and UI verification. For example, TypeScript 7
does not expose the compiler path required by vue-tsc 3.3.11; rebasing a dependency
PR does not make that combination compatible. Review security alerts even when
the required fix involves a major upgrade.

The frontend Docker build prints the installed direct dependency versions before
type checking. Reproduce a failing dependency PR using its actual package.json
and package-lock.json, not just the default branch. After changing the Dependabot
rules on the default branch, use `@dependabot recreate` on an existing generated
PR to regenerate its dependency selection before reviewing the new CI result.

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
