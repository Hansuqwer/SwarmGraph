# COMPLIANCE.md — AI Provider Swarm Gateway

## Compliance Boundary

This project implements a **compliant AI provider routing gateway**. It is designed to help users
make efficient use of AI providers they have legitimately signed up for and configured.

---

## ❌ What This Project Does NOT Do (Prohibited Behaviors)

The following behaviors are **explicitly blocked** by the policy guardrails and are **not implemented** anywhere in this codebase:

| Prohibited Behavior | Status |
|---|---|
| Automatic account creation | ❌ Not implemented. Not scaffolded. |
| Account farming / rotation | ❌ Blocked by `reject_quota_evasion()` |
| CAPTCHA bypass | ❌ Not implemented. Not scaffolded. |
| Fake identity generation | ❌ Not implemented. |
| Scraping private web sessions | ❌ Not implemented. |
| Rotating multiple accounts to bypass free-tier limits | ❌ Blocked. Only one credential per provider. |
| Circumventing rate limits | ❌ Quota tracker enforces limits. |
| Treating "web-only free" as "API free" | ❌ Blocked by `can_route_to_provider()` |
| Using unknown limits as if free | ❌ Blocked by default. User must opt in. |
| Hiding or resetting usage counters | ❌ Counters are append-only. |
| Credential harvesting | ❌ Blocked by `reject_quota_evasion()` |

---

## ✅ What This Project Does (Compliant Behaviors)

| Compliant Behavior | Implementation |
|---|---|
| User-owned API key configuration | `.env` file, env vars only |
| Per-provider credential isolation | One env var per provider |
| Quota-aware routing across user's own providers | `quota_check_node()` |
| Transparent local usage tracking | `QuotaTracker` (JSON file) |
| Explicit audit logs for every routing decision | `GatewayState.audit_log` |
| Policy guardrails that block unsafe behaviors | `policy/guardrails.py` |
| Clear warnings for web-only providers | Registry flags + routing rejects |
| Conservative treatment of unknown limits | `allow_unknown_quota=False` by default |
| Manual sign-up and sign-in links | `providers.yaml`, dashboard |
| Provider dashboard and docs links | CLI dashboard, registry |
| Graceful fallback when quota exhausted | `quota_check_node()` removes exhausted providers |

---

## Provider Terms of Service

Users are responsible for complying with each provider's terms of service.
Key policy concerns are noted in `providers.yaml` under `policy_notes` for each provider.

Notable concerns:
- **Mistral AI free tier**: Prompts may be used for model training. Review their privacy policy before sending sensitive data.
- **Google Gemini free tier**: Review Google's data usage policies for the free tier.
- **All providers**: Verify whether automated API usage is permitted under your account plan.

---

## Reporting Compliance Issues

If you identify a design choice in this project that enables or could enable quota evasion,
account rotation, or other prohibited behaviors, please open an issue with the label `compliance`.
