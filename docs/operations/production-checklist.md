# Production Checklist

Use this checklist before promoting SwarmGraph from local evaluation to a shared or production-like environment.

## Installation And Release Confidence

- Install from a clean checkout with `uv sync --all-extras --dev`.
- Run the supported quality gates before release:
  - `uv run ruff check packages/`
  - `uv run pyright`
  - `uv run pytest packages/swarm-shared/tests packages/hive-swarm/tests packages/ai-provider-swarm-gateway/tests`
  - `uv run python examples/01_smoke_stub_mode.py`
- Build all workspace packages into a single distribution directory and inspect the artifacts before publishing:
  - `uv build --package swarm-shared --out-dir dist`
  - `uv build --package hive-swarm --out-dir dist`
  - `uv build --package ai-provider-swarm-gateway --out-dir dist`

## Configuration

- Keep production configuration outside source control.
- Document the selected provider, model, tenant, quota, consensus, and human-approval settings for each deployment.
- Prefer explicit environment variables over implicit defaults for provider credentials and policy-critical behavior.
- Verify that a clean environment fails safely when required credentials or approval settings are missing.

## Secrets And Credentials

- Store API keys and signing keys in a secrets manager or the hosting platform's encrypted secret store.
- Never commit `.env` files, generated keys, provider credentials, or copied authorization headers.
- Run `make audit-scan` before committing staged changes.
- Rotate any key that has been printed to logs, shared in tickets, or committed even briefly.

## Audit And Compliance Controls

- Enable audit logging for workflows that make regulated, irreversible, or customer-impacting decisions.
- Protect audit log storage from modification by the runtime identity where practical.
- Run `scripts/verify_audit_log.sh` against representative signed audit records before a release.
- Confirm that human-in-the-loop approvals record the approver, prompt, decision, timestamp, and relevant execution identifiers.

## Safety And Policy Checks

- Define which workflows require consensus and which workflows require human approval.
- Set tenant quotas and cost limits before enabling real provider calls.
- Test the failure mode for provider timeout, provider error, quota exhaustion, failed approval, and consensus failure.
- Keep experimental providers, protocols, or orchestration changes behind explicit flags or non-production configuration.

## Operations And Rollback

- Record the package versions, git commit, provider configuration, and deployment environment for each release.
- Keep a rollback path to the previous package set and configuration.
- Monitor request count, latency, provider errors, quota rejection count, approval wait time, and audit write failures.
- Treat audit write failures, unsigned execution records, and unexpected policy bypass as release-blocking incidents.
