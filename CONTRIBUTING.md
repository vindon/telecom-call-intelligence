# Contributing to Telecom Call Intelligence

Thank you for your interest in contributing. This document covers how to set up the project locally, the conventions we follow, and how to submit changes.

---

## Development setup

```bash
git clone https://github.com/vindon/telecom-call-intelligence.git
cd telecom-call-intelligence

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Add your GROQ_API_KEY to .env
```

Verify the setup with a 3-call smoke test:

```bash
python run_pipeline.py --n 3
```

---

## Project conventions

### Code style

- **No unnecessary comments** — code should be self-documenting through naming
- **No docstrings on obvious functions** — one-line doc is acceptable on public module functions where the signature is non-obvious
- **Type hints** — use them on all function signatures
- **Logging** — always use `get_logger(__name__)` from `pipeline.logger`; never `print()` in pipeline modules (print is acceptable in CLI entry points)
- **No f-string logging** — use `log.info("msg %s", var)` not `log.info(f"msg {var}")` (avoids string interpolation on filtered levels)

### Git commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add agent coaching score to aggregator
fix: handle null customer_sentiment_end in QA audit
refactor: extract checkpoint logic to standalone module
docs: update ARCHITECTURE.md with new state schema
chore: bump groq>=0.12.0 in requirements.txt
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

## Submitting a pull request

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Verify the pipeline still works: `python run_pipeline.py --n 3`
4. Run a syntax check: `python -m py_compile pipeline/*.py *.py`
5. Open a pull request against `main` and fill in the PR template

One PR per logical change. Keep commits clean — squash fixup commits before opening.

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
