# Pre-commit Hook

This repository includes a pre-commit hook that automatically runs diagnostic generation before every commit.

## Installation

Run the following command to install the pre-commit hook:

```bash
make install-hooks
```

This will copy `tools/pre-commit` to `.git/hooks/pre-commit` and make it executable.

## What It Does

When you run `git commit`, the hook will:

1. **Check for changes** — If no files have changed since the last build, it skips the build.
2. **Run `python3 build.py`** — This generates the diagnostic artifacts.
3. **Stage diagnostic artifacts** — The most recent `diagnostic/build-XXX.logd` and `diagnostic/build-XXX.json` are automatically staged.
4. **Abort on failure** — If the build fails, the commit is aborted with an error message.

## Why It's Needed

The project requires diagnostic artifacts to be included with every PR. Without this hook, contributors must manually run `python3 build.py` and copy the artifacts, which is easy to forget.

## Bypassing the Hook

If you need to commit without running the hook (e.g., for documentation-only changes):

```bash
git commit --no-verify -m "docs: update README"
```

## Troubleshooting

- **Build takes too long**: The hook prints progress as it runs. Wait for it to complete.
- **Build fails**: Fix the build errors and try again. The commit will be aborted.
- **Hook not running**: Make sure the hook is installed (`make install-hooks`) and executable.
