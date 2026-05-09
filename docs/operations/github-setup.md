# GitHub Repository Setup

These settings require repository admin access and cannot be enforced from CI alone.

## Labels

Labels are defined in `.github/labels.yml`.

Dry-run the sync:

```bash
/opt/homebrew/bin/uv run python scripts/sync_github_labels.py --dry-run
```

Apply with a token that can manage repository metadata:

```bash
GITHUB_TOKEN=... /opt/homebrew/bin/uv run python scripts/sync_github_labels.py
```

The script uses GitHub's REST label endpoints to patch existing labels or create missing labels.

## Security Settings

Enable these in repository settings:

- Code scanning
- Secret scanning
- Push protection
- Dependabot alerts
- Dependabot security updates
- Dependabot version updates

## Branch Protection

Protect `main` with:

- Pull request required before merge
- Required status checks for CI
- Conversation resolution required
- Linear history if preferred by maintainers
- Force pushes disabled
- Deletions disabled
