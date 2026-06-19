# Diagnostic Pre-Commit Hook

The diagnostic pre-commit hook runs `python3 build.py` before each commit that
has staged changes. If the build fails, the hook exits non-zero and blocks the
commit so broken diagnostics are not published accidentally.

## Install

```bash
make install-hooks
```

This copies `tools/pre-commit` to `.git/hooks/pre-commit` and marks it
executable.

## Behavior

- Skips work when there are no staged changes.
- Uses `PYTHON` when set, otherwise prefers `python3`, then `python`.
- Runs `build.py` from the repository root.
- Stages generated diagnostic artifacts from `diagnostic/build-*.logd`,
  `diagnostic/build-*.json`, and `diagnostic/build-*-metadata.json`.
- Aborts the commit if the diagnostic build fails.

## Manual Smoke Check

```bash
git add tools/pre-commit Makefile docs/pre-commit-hook.md
tools/pre-commit
```

On machines without every language toolchain, `build.py` may report module
failures or diagnostic finalization errors. The hook intentionally preserves
that failure signal and blocks the commit until the diagnostics are fixed or the
maintainer explicitly bypasses the hook for a known local-environment issue.
