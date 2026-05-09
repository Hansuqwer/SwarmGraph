# Provenance Archive

This directory preserves SwarmGraph's build history, orchestrator prompts, patch
handover notes, analysis bundles, and migration notes that produced SwarmGraph
v0.8.0 and later hardening passes.

These files are not required reading for normal users. They exist so auditors and
maintainers can reconstruct how the project evolved and which agent-generated
artifacts informed each implementation pass.

Use the curated project history first:

- root `CHANGELOG.md` for release notes
- root `README.md` for user-facing positioning
- `docs/architecture/overview.md` for current design

Archive contents:

- `patches/`: patch deliverables v2-v8 verbatim
- `orchestrator-prompts/`: prompt history
- `analysis-2026-05-07/`: original hive analysis bundle
- `milestones/`: milestone documents when present
- `consensus_logs/`: preserved consensus logs
