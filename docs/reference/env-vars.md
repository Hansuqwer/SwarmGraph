# Environment Variables

| Variable | Purpose |
|---|---|
| `AI_PROVIDER_GATEWAY_TENANT` | Default tenant scope |
| `HIVE_SWARM_LLM_BACKEND` | `stub` or `gateway` |
| `HIVE_SWARM_LLM_PROVIDER` | Default gateway provider id |
| `HIVE_SWARM_LLM_MODEL` | Default gateway model id |
| `HIVE_SWARM_LLM_STREAM` | Enable streaming worker dispatch |
| `HIVE_SWARM_COST_TRACKING` | Enable/disable cost tracking |
| `HIVE_SWARM_AUDIT_SECRET` | HMAC secret for audit signing |
| `AI_PROVIDER_GATEWAY_REVIEWER_ID` | Reviewer id for HITL CLI prompts |
| `AI_PROVIDER_GATEWAY_STATE_DIR` | Optional production confinement base for CLI quota storage paths |
| `AI_PROVIDER_GATEWAY_USAGE_PATH` | Override local quota usage JSON path |
| `AI_PROVIDER_GATEWAY_VAULT_KEY` | Fernet key for encrypted account vault |
| `AI_PROVIDER_GATEWAY_9ROUTER_API_KEY` | Primary 9router API key |
| `AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL` | 9router OpenAI-compatible base URL |
| `AI_PROVIDER_GATEWAY_9ROUTER_MODEL` | 9router model override |
| `AI_PROVIDER_GATEWAY_9ROUTER_TIMEOUT` | 9router non-streaming request timeout |
| `AI_PROVIDER_GATEWAY_9ROUTER_ALLOWED_HOSTS` | Optional comma-separated host allowlist for 9router base URL |
| `AI_PROVIDER_GATEWAY_9ROUTER_ALLOW_OPENAI_KEY` | Explicit opt-in to use `OPENAI_API_KEY` as 9router key |
| `ROUTER_API_KEY` / `NINEROUTER_API_KEY` / `KILO_CODE_API_KEY` | 9router compatibility key aliases |
| `OPENAI_API_KEY` | OpenAI adapter key; only used by 9router when opt-in flag above is truthy |
| `ANTHROPIC_API_KEY` | Anthropic adapter key |
| `GROQ_API_KEY` | Groq adapter key |
| `OPENROUTER_API_KEY` | OpenRouter adapter key |
| `XAI_API_KEY` / `AI_PROVIDER_GROK_API_KEY` | Grok/xAI adapter key aliases |
| `QWEN_API_KEY` | Qwen adapter key |
| `MOONSHOT_KIMI_API_KEY` | Kimi adapter key |
| `GOOGLE_API_KEY` | Google Gemini adapter key |
| `DEEPSEEK_API_KEY` | DeepSeek adapter key |
| `ZHIPU_GLM_API_KEY` | GLM adapter key |
