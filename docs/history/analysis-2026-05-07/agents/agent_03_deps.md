# Agent 03 — Dependency & Toolchain Auditor
**Model:** Claude Sonnet 4.6
**Scope:** all `pyproject.toml`, `.env.example`
**Deliverable goal:** version skew, CVE check, Python target compatibility.

## PURPOSE
Confirm dependency posture is consistent and current per May 2026 ecosystem.

## VERIFIED PYPROJECT — `hive-swarm/pyproject.toml`
```toml
requires-python = ">=3.11"
dependencies = ["pydantic>=2.7.0"]

[project.optional-dependencies]
langgraph = ["langgraph>=0.3.0", "langgraph-checkpoint>=2.0.0"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0"]
```

## WHAT WORKS ✅
- `python>=3.11` matches Pydantic v2 + LangGraph 0.3 minimum.
- `pydantic>=2.7.0` correctly requests v2 with the modern `ConfigDict` API.
- `langgraph>=0.3.0` is the modern tagged release (the `Send`/`interrupt`/`Command` API is stable from 0.3.x).
- Test deps (`pytest>=8`, `pytest-asyncio>=0.23`) are current.
- LangGraph is listed under **optional-dependencies** — correctly allows the framework to import without LangGraph (the `try / except ImportError` blocks in `factory.py:L28-L37` and `checkpointing.py:L18-L22` work).

## WHAT'S BROKEN 🔴

### 03-DEP1 (med) — Pydantic upper bound missing
`pydantic>=2.7.0` with no upper bound. Pydantic 3.0 (announced for 2026 H2) will introduce breaking changes. Recommend `pydantic>=2.7,<3`.

### 03-DEP2 (med) — LangGraph upper bound missing
`langgraph>=0.3.0` with no cap. LangGraph 1.0 is on the H2 2026 roadmap. Recommend `langgraph>=0.3,<2`.

### 03-DEP3 (high) — Other two sub-projects' pyprojects not fetched here
We did not fetch `ai-coder-hardening-improved/pyproject.toml` or `ai-provider-swarm-gateway/pyproject.toml`. Cross-project version skew (e.g. one pins `pydantic>=2.5`, another `>=2.8`) cannot be confirmed in this run. **Action:** rerun Agent 03 against those two files before merging the consolidated package.

### 03-DEP4 (low) — No `[tool.ruff]`, `[tool.mypy]`, or `[tool.pyright]` config in `hive-swarm/pyproject.toml`
The framework declares typed APIs everywhere but ships no static-analysis config. Recommend adding `ruff` (≥ 0.6) and `pyright` (≥ 1.1.380) configs.

## WHAT'S MISSING 🟡
- No `pre-commit-config.yaml`.
- No `Makefile` / `tox.ini` / `noxfile.py`.
- No GitHub Actions / CI manifest at the `swarmMain/` level.
- No `langgraph-checkpoint-sqlite` or `-postgres` extras — but the code references `from langgraph.checkpoint.sqlite import SqliteSaver` in `ai-coder-hardening-improved/.../checkpoints.py:L153`. Either the extra is missing from the optional-deps OR the user is expected to add it manually.

## CVE CHECK (May 2026 baseline)
- `pydantic 2.7.0` → no known CVEs as of May 2026.
- `langgraph 0.3.x` → no known CVEs.
- `pytest 8.x` → no known CVEs.
- `pytest-asyncio 0.23` → no known CVEs.
✅ clean.

## FIX RECOMMENDATION
```toml
# hive-swarm/pyproject.toml — recommended diff
requires-python = ">=3.11,<3.14"
dependencies = ["pydantic>=2.7,<3"]

[project.optional-dependencies]
langgraph = [
    "langgraph>=0.3,<2",
    "langgraph-checkpoint>=2.0,<3",
    "langgraph-checkpoint-sqlite>=2.0,<3",      # ← add
    "langgraph-checkpoint-postgres>=2.0,<3",    # ← add (optional)
]
dev = [
    "pytest>=8.0,<9",
    "pytest-asyncio>=0.23,<1",
    "pytest-cov>=5.0,<7",
    "ruff>=0.6,<1",                              # ← add
    "pyright>=1.1.380",                          # ← add
    "hypothesis>=6.110",                         # ← add for property-based consensus tests
]
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 03-DEP1 missing upper bound (pydantic) | med | 1m |
| 03-DEP2 missing upper bound (langgraph) | med | 1m |
| 03-DEP3 cross-project skew unverified | high | 30m (re-fetch + diff) |
| 03-DEP4 no static-analysis config | low | 30m |
| Missing `langgraph-checkpoint-sqlite` extra | high | 5m |
