# swarm-shared API

::: swarm_shared.audit

::: swarm_shared.audit_backends

::: swarm_shared.redaction

## Patch Redaction

`swarm_shared.redaction.redact_patch()` redacts secrets in unified diffs while preserving patch headers and hunk markers:

```python
from swarm_shared.redaction import redact_patch

safe_patch = redact_patch(patch_text)
```

Use this before storing or sharing generated patches that may contain provider keys, bearer tokens, DSNs, or other secrets.

::: swarm_shared.pricing
