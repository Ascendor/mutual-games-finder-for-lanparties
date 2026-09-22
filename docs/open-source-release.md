# Open-source release preparation

This procedure intentionally separates code preparation from destructive Git
history rewriting. Keep the existing repository private until every check is
complete.

## Recommended: create a clean public repository

The safest publication path is a new repository containing only the reviewed
tree and no previous commits:

```bash
git archive --format=tar HEAD | tar -xf - -C ../mutual-games-finder-public
cd ../mutual-games-finder-public
git init
git add .
git commit --signoff -m "Initial open-source release"
```

Before pushing, verify that no database, backup, `.env`, provider token, log,
or real participant identifier is present. Keep the old repository private as
an internal development archive.

## Alternative: rewrite the existing repository

Use this only if preserving public commit history is important. Every clone,
branch, and tag containing old objects must be replaced. Coordinate this with
all collaborators.

1. Make an encrypted private mirror backup outside the repository.
2. Install `git-filter-repo` from its official distribution.
3. Work from a fresh mirror clone.
4. Remove the historical database:

   ```bash
   git filter-repo \
     --path backups/lan_party_game_finder_pre_postgres_2026-06-29.db \
     --invert-paths
   ```

5. Replace the historical shared development password using a local replacement
   file that must not itself be committed:

   ```text
   literal:OLD_PASSWORD==>REMOVED_LEGACY_SHARED_PASSWORD
   ```

   ```bash
   git filter-repo --replace-text ../history-replacements.txt
   ```

6. Optionally use a mailmap callback to replace personal commit email addresses.
7. Search the rewritten object database and inspect every tag before pushing.
8. Force-push all rewritten branches and tags only after the private backup is
   verified.
9. Delete old release archives and cached downloadable artifacts. Inform every
   collaborator that old clones must be discarded rather than merged.

If the repository was publicly accessible before rewriting, assume old objects
may have been copied. Rewriting reduces future exposure but cannot revoke
existing clones. Assess any disclosure of personal data separately.

## Release gate

- Complete `docs/open-source-compliance.md`.
- Confirm dependency audits report no unresolved high or critical findings.
- Confirm SBOMs and third-party notices match all three application components.
- Run a history secret scan and review binary files manually.
- Verify production starts with unofficial provider integrations disabled.
- Verify generated passwords are required and no shared default exists.
- Review `SECURITY.md`, `PROVIDERS.md`, `/legal`, and deployment documentation.
