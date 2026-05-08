# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.8.x (main) | Yes |
| < 0.8.0 | No — upgrade to main |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report via [GitHub Security Advisories](https://github.com/Hansuqwer/SwarmGraph/security/advisories/new).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We aim to acknowledge reports within 48 hours and publish a fix within 14 days for critical issues.

---

## Token Hygiene — Critical

This project has a recurring credential-leak risk because LLM API keys are used during development and testing.

**Rules:**

1. **Never paste API keys, tokens, or secrets into issues, PRs, comments, or chat.** The framework reads credentials from environment variables only — you never need to paste a real key anywhere in the repo.

2. **Environment variable names only appear in code**, never values. Example correct usage:
   ```python
   secret = os.environ.get("HIVE_SWARM_AUDIT_SECRET")
   ```

3. **If you accidentally expose a credential**, rotate/revoke it immediately — assume it is compromised the moment it appears in any public channel.

4. **Pre-commit check** — run before every push:
   ```bash
   git diff --cached | grep -iE \
     'sk-[a-z0-9]{20}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|Bearer [a-zA-Z0-9]{20,}'
   ```
   Zero output = safe to push.

5. **The `.gitignore` excludes** `.env`, `*.env`, `*_secrets.*`, `.venv/`. Do not force-add these.

---

## Audit Log Verification

SwarmGraph v0.8.0+ supports HMAC-SHA256 signed audit logs. See:

- [Audit signing architecture](docs/architecture/audit-signing.md)
- [Audit verification operations guide](docs/operations/audit-verification.md)

To verify a log:
```bash
HIVE_SWARM_AUDIT_SECRET=<secret> \
uv run ai-provider-gateway audit verify path/to/audit.jsonl
```

Exit code 0 = chain intact. Non-zero = tampered or wrong secret.

---

## Dependency Security

Dependencies are pinned in `uv.lock`. Run periodically:
```bash
uv lock --upgrade          # update lockfile
uv run pip-audit           # audit for CVEs (pip-audit in dev deps)
```
