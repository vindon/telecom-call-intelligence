# Contributing to Telecom Call Intelligence

This is a proprietary project (Copyright © 2026 Vinoth N). Contributions are welcome from authorised team members only.

---

## Development Setup

```bash
git clone https://github.com/vindon/telecom-call-intelligence.git
cd telecom-call-intelligence
python -m venv .venv && source .venv/bin/activate
make install-dev          # installs prod + dev deps and pre-commit hooks
cp .env.example .env      # add ANTHROPIC_API_KEY (required) + optional NVIDIA_API_KEY
```

Verify setup:

```bash
make test          # 342 unit tests — should all pass in < 7 seconds
make run           # 3-call smoke test (requires ANTHROPIC_API_KEY in .env)
```

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-stable; protected; no direct pushes |
| `develop` | Integration branch for feature merges |
| `feat/*` | New features or agents |
| `fix/*` | Bug fixes |
| `chore/*` | CI, deps, tooling, docs |

Pre-commit blocks direct commits to `main`.

---

## Project Conventions

### Code style

- **All constants** must live in `pipeline/config.py` — not scattered across modules
- **Agents are stateless** — `run(state: dict) -> dict`; never store data on `self`
- **State is immutable** — always `return {**state, "new_key": value}`; never mutate in-place
- **No unnecessary comments** — code should be self-documenting through naming
- **No docstrings on obvious functions** — one-line module header is acceptable
- **Type hints** — use them on all function signatures
- **Logging** — always use `get_logger(__name__)` from `pipeline.logger`; never `print()` in pipeline modules
- **No f-string logging** — use `log.info("msg %s", var)` not `log.info(f"msg {var}")`

### Git commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add agent coaching score to aggregator
fix: handle null customer_sentiment_end in QA audit
refactor: extract checkpoint logic to standalone module
docs: update ARCHITECTURE.md with new state schema
chore: bump google-genai>=1.1.0 in requirements.txt
```

### Branch naming

```
feat/agent-coaching-score
fix/null-sentiment-qa-crash
refactor/checkpoint-module
docs/architecture-update
```

---

## What to work on

Check the [open issues](https://github.com/vindon/telecom-call-intelligence/issues) for the backlog. Issues tagged `good first issue` are a good starting point.

If you want to propose a significant change, open an issue first to discuss the approach before writing code.

---

## Adding a New Agent

See `CLAUDE.md` for the full checklist. In brief:

1. `pipeline/agents/your_agent.py` — stateless class, `run(state: dict) -> dict`
2. Instrument with `DecisionLogger` (see `CLAUDE.md`) — mandatory for all agents
3. Export from `pipeline/agents/__init__.py`
4. Wire the node and edges in `pipeline/graph.py`; update `PipelineState`
5. Write tests in `tests/` including `DecisionLogger` assertions
6. Update `ARCHITECTURE.md` and `CHANGELOG.md`

---

## Submitting a Pull Request

1. Branch from `develop` — not from `main`
2. Run `make check` (lint + type-check + test) — CI must be green
3. Open a PR against `develop` and fill in the PR template
4. One approval required before merge

One PR per logical change. Squash fixup commits before opening.

---

## Prompt changes

Changes to `prompts/system_prompt.txt` require:

1. A QA audit run before and after showing no regression in the average score
2. An explanation of why the change improves extraction accuracy
3. Evidence from at least 3 sample transcripts showing the new behavior

Include the QA score comparison (before/after) in the PR description.

---

## Adding a new dashboard panel

1. Add the computation to `pipeline/aggregator.py` under the relevant section
2. Add the corresponding key to `outputs/summary.json` schema (update `ARCHITECTURE.md`)
3. Add the chart to `dashboard/app.py` following the existing two-call `update_layout` pattern
4. Verify there are no Plotly keyword-argument conflicts (the project uses Plotly 6.7+)

---

## Questions

Open a [GitHub Discussion](https://github.com/vindon/telecom-call-intelligence/discussions) for general questions. Use [Issues](https://github.com/vindon/telecom-call-intelligence/issues) for bugs and feature requests.
