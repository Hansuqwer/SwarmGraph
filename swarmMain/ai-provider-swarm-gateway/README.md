# 🤖 AI Provider Swarm Gateway

A **safe, compliant, auditable** AI provider routing gateway built with **Pydantic v2 + LangGraph + swarm consensus**.

> ⚠️ **COMPLIANCE WARNING**: This tool routes requests across AI providers using **your own legitimate credentials only**. It does not enable account rotation, quota evasion, account farming, CAPTCHA bypass, or any unauthorized automation. See [COMPLIANCE.md](COMPLIANCE.md).

---

## What It Does

- Discovers AI providers with verified free/trial/paid API tiers
- Routes your requests across providers you configure with your own API keys
- Enforces policy guardrails to prevent quota abuse
- Tracks usage locally (no hidden counters, no cloud telemetry)
- Provides a Rich CLI dashboard and optional Streamlit UI
- Works fully offline with mock provider (no credentials needed for testing)

## Verified Free-Forever Providers (as of May 2026)

| Provider | Daily Free | Requires Card |
|---|---|---|
| Google Gemini (AI Studio) | 100–1000 req/day | No |
| Groq | 1000–14400 req/day | No |
| Mistral AI | 1B tokens/month | No |
| Cerebras | 1M tokens/day | No |
| Cohere | 1000 req/month | No |
| Cloudflare Workers AI | 10K neurons/day | No |
| Ollama (Local) | Unlimited | No |
| LM Studio (Local) | Unlimited | No |

*All limits must be verified at provider documentation before use. Data may change.*

---

## Installation

```bash
git clone <repo>
cd ai-provider-swarm-gateway
pip install -e ".[langgraph,test]"
```

## Environment Variable Setup

```bash
cp .env.example .env
# Edit .env with your own API keys from each provider's official site
```

Never commit `.env` to version control.

## Running the CLI Dashboard

```bash
# Show free-tier overview table
ai-provider-gateway dashboard

# Show provider links (sign-up, docs, dashboard)
ai-provider-gateway dashboard --links

# List only providers with confirmed free API
ai-provider-gateway list-free
```

## Running a Mock Gateway Request

```bash
# No credentials needed — uses mock provider
ai-provider-gateway run "What is the capital of France?"

# Prefer a specific provider (if configured)
ai-provider-gateway run "Hello" --provider groq
```

## Running Tests

```bash
pytest tests/ -v
# All tests pass without credentials using mock provider
```

## How Routing Works

```
Request → Intake (validate) → Classify (detect capability)
        → Filter (capability + credentials + policy)
        → Quota Check (local usage counters)
        → Swarm Route (score each candidate)
        → Consensus (cost-aware + policy-guarded)
        → Provider Call → Validate → Update Usage → Response
```

**Priority order:**
1. Reject unsafe request metadata
2. Reject providers blocked by policy
3. Reject providers without credentials
4. Reject providers with exhausted quota
5. Reject providers with unknown quota (unless user opts in)
6. Prefer verified free API providers
7. Prefer local providers (no cost, no rate limit)
8. Prefer user-preferred provider
9. Fall back to any remaining legitimate provider

## How Quota Tracking Works

- Stored at `~/.ai_provider_gateway/usage.json`
- Incremented per successful request (append-only)
- Resets if `reset_at` timestamp has passed
- Unknown limits treated conservatively (not routed as free)
- View current usage: `ai-provider-gateway quota`

## How to Add a Provider

1. Add entry to `src/ai_provider_swarm_gateway/registry/providers.yaml`
2. Create adapter in `src/ai_provider_swarm_gateway/providers/yourprovider_adapter.py`
3. Register adapter in `graph/nodes.py::_get_adapter()`
4. Add env var to `.env.example`
5. Run tests

## How to Review Provider Data

Each provider entry in `providers.yaml` includes:
- `confidence`: `verified | partially_verified | unknown | likely_changed`
- `last_verified`: ISO date of last manual verification
- `source_links`: URLs used for research
- `policy_notes`: Any compliance concerns

Always manually verify limits before production use.

## Streamlit Dashboard (Optional)

```bash
pip install ".[dashboard]"
python -c "from src.ai_provider_swarm_gateway.dashboard.app import launch_streamlit; launch_streamlit()"
```

## See Also

- [PROJECT_REVIEW.md](PROJECT_REVIEW.md) — Full project review for AI and human auditors
- [COMPLIANCE.md](COMPLIANCE.md) — Compliance boundary and prohibited behaviors
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture
- [PROVIDER_REGISTRY.md](PROVIDER_REGISTRY.md) — Provider data and research sources
- [SETUP.md](SETUP.md) — Detailed setup instructions
