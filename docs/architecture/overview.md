# Architecture Overview

SwarmGraph has three packages:

- `swarm-shared`: low-level reusable primitives.
- `hive-swarm`: LangGraph swarm runtime.
- `ai-provider-swarm-gateway`: provider registry, quota, CLI.

The runtime decomposes a user objective into tasks, sends tasks to workers, converts worker outputs to votes, runs consensus, optionally triggers HITL, and returns a final output.
