# Keys to clean before GitHub push

> 2026-07-21

## 🔴 CRITICAL — Must replace with env var or remove

| File | Line | Content | Action |
|------|------|---------|--------|
| `gateway/provider.yaml` | 13 | `api_key: sk-20d...743d` | 🔴 Replace with `${DEEPSEEK_API_KEY}` |
| `gateway/provider.yaml` | 29 | `api_key: sk-921...0be` | 🔴 Replace with `${OPENAI_API_KEY}` |
| `switch/provider.yaml` | 13,29 | (same provider config) | 🔴 Same as above |

## 🟡 MEDIUM — Test credentials (change or remove)

| File | Line | Content | Action |
|------|------|---------|--------|
| `core/agent/v4/api.py` | 48 | `AUTH_TOKEN = "dev-token"` | 🟡 Add to `.env` |
| `core/agent/v4/api.py` | 49 | `ADMIN_TOKEN = "admin-token"` | 🟡 Add to `.env` |
| `core/agent/v4/api.py` | 178 | `"api_key": "not-needed"` | 🟡 Change to env var |
| `core/agent/v4/api_gateway.py` | 165 | `Bearer {SWITCH_KEY}` → `dm-client` | 🟡 Obfuscate |
| `gateway/provider.yaml` | 203 | `- not-needed` | 🟡 Remove or change |
| `gateway/provider.yaml` | 204 | `admin_token: admin-test` | 🟡 Change |
| `config/user_config.yaml` | 73 | `api_key: "sk-xxx...xxxx"` | 🟡 Replace with `${DEEPSEEK_API_KEY}` |

## 🟢 LOW — Documentation references (OK to push)

| File | Lines | Content |
|------|-------|---------|
| `config/user_config.yaml` | 71-72 | Documentation comments about API keys |
| `core/agent/llm_providers/openai_provider.py` | 11 | Docstring |
| `core/agent/v3_2/deepseek_provider.py` | 4 | Example comment |
| `core/agent/mcp/security.py` | 132 | Comment |
| Various | Bearer headers | Standard HTTP — fine |
