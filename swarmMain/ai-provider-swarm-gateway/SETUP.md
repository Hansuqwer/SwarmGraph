# SETUP.md — Installation & Configuration

## Requirements
- Python 3.11+
- pip or uv

## Install (Development)
```bash
pip install -e ".[langgraph,test]"
```

## Install (Production with all providers)
```bash
pip install -e ".[all]"
```

## Configure Credentials
```bash
cp .env.example .env
# Edit .env — set only the providers you have signed up for
```

## Load Environment
```bash
source .env  # or use python-dotenv (auto-loaded by the gateway)
```

## Run Tests (no credentials needed)
```bash
pytest tests/ -v
```

## Run CLI Dashboard
```bash
ai-provider-gateway dashboard
ai-provider-gateway list-free
```

## Run a Mock Request
```bash
ai-provider-gateway run "Explain photosynthesis"
```

## Run with Real Provider
```bash
export GROQ_API_KEY=your_key_here
ai-provider-gateway run "Hello world" --provider groq
```

## Provider Sign-Up Links
See `providers.yaml` or run `ai-provider-gateway dashboard --links`
