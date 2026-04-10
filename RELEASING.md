# Releasing Mem-Wiz

This project publishes from GitHub Releases only.

The release workflow expects a normal version bump followed by a git tag push.
The example tag in this document is `v0.1.2`, but use the next SimVer value for
the actual release.

## Maintainer Checklist

1. Apply the version bump in both `pyproject.toml` and `src/mem-wiz/memwiz/__init__.py`.
2. Run `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q`.
3. Build the bundle locally with `.venv/bin/python scripts/build_skill_artifact.py`.
4. Confirm the artifact name matches `mem-wiz-skill-<version>.zip`.
5. Generate or verify the companion `.sha256` checksum file for the zip artifact.
6. Commit the release metadata changes.
7. Create and push the release tag, for example `git tag v0.1.2` followed by `git push origin v0.1.2`.

## Workflow Behavior

Pushing a `v*` tag triggers `.github/workflows/release.yml`.

That workflow:

- runs the full test suite
- builds `mem-wiz-skill-<version>.zip`
- generates `mem-wiz-skill-<version>.zip.sha256`
- creates the matching GitHub release
- uploads both release assets

## Updater Contract

`memwiz self-update` expects these exact GitHub release assets:

- `mem-wiz-skill-<version>.zip`
- `mem-wiz-skill-<version>.zip.sha256`

If either asset name changes, the updater contract must be updated in code and
tests at the same time.
