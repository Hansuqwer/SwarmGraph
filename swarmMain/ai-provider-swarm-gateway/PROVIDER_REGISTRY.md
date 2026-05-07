# PROVIDER_REGISTRY.md — Provider Research Summary

**Last Verified**: 2026-05-07  
**Sources**: apiscout.dev, awesomeagents.ai, softtechhub.us, dev.to/bd_perez, belski.me, cheahjs/free-llm-api-resources, Alibaba Cloud docs

---

## Tier 1: Permanent Free API (No Credit Card, No Expiry)

| Provider | Daily Free | Monthly Free | Requires Card | Notes |
|---|---|---|---|---|
| **Google Gemini** | 100–1000 req/day | 250K TPM | No | Best free frontier model. 5-15 RPM. |
| **Groq** | 1000–14400 req/day | — | No | Ultra-fast LPU. 30-60 RPM. |
| **Mistral AI** | — | 1B tokens | No (phone verify) | ⚠️ Prompts may be used for training. |
| **Cerebras** | 1M tokens/day | — | No | 14,400 RPD on 8B model. |
| **Cohere** | — | 1000 req/month | No | Very restrictive. Evaluation only. |
| **Cloudflare Workers AI** | 10K neurons/day | — | No | Edge inference. |
| **Zhipu GLM** | unknown | unknown | No | ⚠️ Limits undocumented. Verify manually. |

## Tier 2: One-Time Credits (Expire or Consume)

| Provider | Credit | Expiry | Notes |
|---|---|---|---|
| **DeepSeek** | 5M tokens | — | One-time. Very cheap after. |
| **xAI (Grok)** | $25 | Expires | One-time signup credit. |
| **NVIDIA NIM** | 1000 credits | Expires | Developer program. |
| **Fireworks AI** | ~$1 | Expires | Not a permanent free tier. |
| **Qwen / Alibaba** | 1M tokens/model | 90 days | Singapore region ONLY. |

## Tier 3: No Free API Tier (Paid Only)

| Provider | Notes |
|---|---|
| **OpenAI** | Free trial credits phased out mid-2025. Requires payment. ChatGPT web is NOT API access. |
| **Anthropic** | No permanent free API. claude.ai web free ≠ API access. ~$5 trial credit on new accounts. |
| **Together AI** | No free tier as of 2026. Requires $5 minimum deposit + credit card. |
| **Perplexity** | API free tier unconfirmed. Web app free ≠ API access. |

## Tier 4: Local / Self-Hosted (Unlimited, Free)

| Provider | Notes |
|---|---|
| **Ollama** | Local. Unlimited. Private. GPU/CPU limited. |
| **LM Studio** | Local. Unlimited. OpenAI-compatible server. |

## Confidence Labels Used in Registry

- `verified` — Confirmed from 2+ sources, direct documentation
- `partially_verified` — Confirmed from 1 source or docs unclear
- `unknown` — Could not confirm. Do NOT treat as free without manual check.
- `likely_changed` — Was verified but flagged as potentially stale

## Research Sources

- https://apiscout.dev/guides/free-ai-apis-developers-2026 (March 2026)
- https://awesomeagents.ai/tools/free-ai-inference-providers-2026/ (April 2026)
- https://softtechhub.us/2026/04/05/list-of-free-ai-apis/ (April 2026)
- https://dev.to/bd_perez/save-money-on-ai-using-those-permanent-free-llm-apis-19ec (March 2026)
- https://belski.me/blog/ai_inference_providers_2026_free_tier_deep_dive/ (April 2026)
- https://github.com/cheahjs/free-llm-api-resources (May 2026)
- https://www.alibabacloud.com/help/en/model-studio/new-free-quota (March 2026)
- https://felloai.com/deepseek-pricing/ (May 2026)
