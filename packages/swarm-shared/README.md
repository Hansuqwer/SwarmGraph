# swarm-shared

Shared primitives for SwarmGraph packages.

Includes:

- Audit signing (`swarm_shared.audit`)
- Atomic writes (`swarm_shared.atomic_write`)
- Bounded lists (`swarm_shared.bounded_list`)
- Pricing (`swarm_shared.pricing`)
- Redaction (`swarm_shared.redaction`)
- Checkpoint helpers (`swarm_shared.checkpointing`)

```bash
pip install swarm-shared
```

Run package tests:

```bash
pytest packages/swarm-shared/tests
```
