# Engineering Standards

What this repo actually does, and where — not an aspirational checklist. Every
claim below names the file that enforces it. If a claim and the file disagree,
trust the file and open an issue against this doc.

Framed against three references used to audit this repo (2026-09-25):
**mattpocock-skills** (`codebase-design` — deep modules, duplication, dead
code), **CodeWalnut's Agentic SDLC** competencies (toolchain setup, context
engineering, evidence-led PRs, token economics, agentic refactoring), and
Claude Code's own conventions (`CLAUDE.md`, hooks, skills). Full audit and
remediation: `CHANGELOG.md` [4.6.0] and [4.7.0].

---

## 1. Toolchain setup — project rules, hooks, guardrails

| Practice | Where |
|---|---|
| AI-assistant working contract (architecture, conventions, do-not-do list) | `CLAUDE.md` |
| Pre-write guard: blocks Edit/Write to `.env` and raw `outputs/*.json\|csv` | `.claude/settings.json` (PreToolUse hook) |
| Post-write formatter: `ruff format` + `ruff check --fix` on every `.py` save | `.claude/settings.json` (PostToolUse hook) |
| Scaffolding skill for adding a new agent (file + graph wiring + test + docs reminder) | `.claude/skills/new-agent` |
| Batch-run and Langfuse-tracing skills | `.claude/skills/batch-run`, `.claude/skills/langfuse` |
| Security-focused review subagent | `.claude/agents/security-reviewer.md` |
| One command for the full local pre-push gate | `make check` → lint + type-check + test |

**Why hooks, not just docs:** a rule in `CLAUDE.md` is a request; a hook is
enforced. The `.env`/`outputs/*.json` guard exists because those are exactly
the files an assistant could plausibly edit by mistake while iterating —
the hook makes that class of mistake impossible instead of relying on the
assistant remembering not to.

---

## 2. Context engineering — single source of truth

| Constant class | Lives in | Never redefined in |
|---|---|---|
| Models, budget, thresholds, timeouts | `pipeline/config.py` | any agent or script |
| LLM client construction (`timeout=`, `max_retries=1`) | `pipeline/llm_clients.py` | `analyzer.py`, `agents/*.py`, `vector_memory.py`, `api/main.py`, `demo/app.py` (all delegate here — see `CHANGELOG.md` [4.6.0]) |
| Provider-unavailability circuit breaker | `pipeline/circuit_breaker.py` | shared by the Gemini-quota and NVIDIA-unavailable breakers, was two copies before [4.6.0] |
| Output directory path | `pipeline.config.OUTPUT_DIR` | never a hardcoded `"outputs"` string |

`docs/decision-logging.md` and `docs/qa-data-quality-gate.md` are the
canonical explanations of the decision-trace contract and the QA-Score-vs-
Data-Quality-Gate distinction, respectively — read before touching either
system rather than re-deriving the reasoning from code.

---

## 3. Test automation

| Gate | Command | Enforced in |
|---|---|---|
| Unit tests (no API calls) | `pytest tests/ -m "not slow and not integration"` | CI (`.github/workflows/ci.yml`), pre-push (`make check`) |
| Coverage floor | `--cov-fail-under=85` (actual: ~91%) | CI, `make test-cov` |
| Lint | `ruff check` | CI, pre-commit, `make lint` |
| Type-check | `mypy pipeline/ --ignore-missing-imports`, `check_untyped_defs=true` | CI, `make type-check` (added to CI in [4.7.0] — previously local-only) |
| SAST / secrets | `semgrep --config=p/security-audit --config=p/secrets` | CI, pre-commit (isolated env — see `.pre-commit-config.yaml` comments on why) |
| Docs/version drift | `scripts/check_docs_sync.py` | CI, pre-commit (added in [4.7.0]) |
| Cross-run KPI drift | `pipeline/drift.py` (`DriftGuard`), tested in `tests/test_drift.py` | Wired into `ExportAgent`, every run — detection/reporting only, not a CI gate (added in [4.8.0]) |
| Golden-set extraction eval | `make eval-golden` (`eval_golden_set.py`), tested in `tests/test_eval_golden_set.py` | Manual only — real API calls (~$0.11), never wired into CI (added in [4.8.0]). **Harness is ready; `evals/golden_set.json` itself has not been generated yet** — a one-time, deliberately-deferred human decision (dataset licensing/PII review); run `make build-golden-set SOURCE=<path>` first, or `make eval-golden` prints a clear message instead of crashing. Also scores first-pass extraction only (no ReAct gap-fill pass) — a golden case whose original run needed gap-fill may show a false regression, a known limitation. |

**Coverage is uneven by design, not by accident.** Pure-logic modules
(`governance.py`, `config.py`, `memory.py`, `circuit_breaker.py`) sit at
100%. The lowest-coverage modules as of [4.7.0] are `analyzer.py` (73%) and
`hf_loader.py`/`vector_memory.py` (63–76%) — these have real untested edges
(Gemini-specific retry paths, HF dataset streaming edge cases) that are
lower-priority than they look, because the two most architecturally
load-bearing files — `graph.py` (routing) and `insights_agent.py`
(provider fallback chain) — were the ones actually raised to ~99%/98% in
[4.7.0]; test effort should follow architectural risk, not just chase the
lowest number on the coverage table.

---

## 4. Token economics — no cost leakage, no silent retries

- **Every LLM client is constructed with an explicit `timeout=` and
  `max_retries=1`** (`pipeline/llm_clients.py`) — the SDK's own retry
  (default 2) is deliberately disabled because it compounds with the
  application-level retry below, and that compounding once nearly hit
  `orchestrator.py`'s 600s subprocess timeout.
- **Application-level retry is bounded and explicit**, not the SDK's:
  `analyzer.py::analyze_transcript` retries a single extraction call up to
  `max_retries=3` times with exponential backoff, only on JSON-decode
  errors or transient rate-limit/5xx responses — every attempt is logged
  with an attempt counter, and the loop gives up cleanly (returns `None`)
  rather than retrying forever.
- **No auto-retry across batch failures.** `Orchestrator.run()` halts the
  *entire* multi-batch run on the first task failure and writes
  `outputs/.halted_for_human_review.json`, requiring `--acknowledge-halt`
  to proceed. This replaced an auto-retry loop that silently doubled spend
  on a hung batch in production (`CLAUDE.md`, "Strict failure policy").
  **No config flag re-enables auto-retry.**
- **Circuit breakers stop a known-down provider from re-paying its own
  timeout every subsequent call.** Once NVIDIA times out once,
  `insights_agent.py` skips straight to Claude for the rest of the run
  (`pipeline/circuit_breaker.py`) — a quota `429`, which is transient, does
  *not* trip the breaker; only a genuine timeout does (see
  `tests/test_agents/test_insights_agent.py::TestNvidiaCall`).
- **`BudgetGuard` reads `BUDGET_USD` from config** and is checked by
  `governance.py` independently of the above — a hard ceiling, not just
  resilience engineering.

This was independently re-verified during the [4.7.0] audit by reading
every retry/timeout call site — confirmed intentional and correctly scoped,
no changes needed.

---

## 5. Dependency management — reproducible installs

- `requirements.txt` / `requirements-dev.txt` / `requirements-dashboard.txt`
  are the **human-edited abstract specs** (loose `>=` bounds, for readability
  and upgrade headroom).
- `requirements*.lock` are the **fully pinned, universal (cross-platform,
  Python 3.11+) resolutions**, generated via `make lock` (uses `uv pip
  compile --universal --python-version 3.11`). CI, `make install`/
  `install-dev`, and the Render deployment (`render.yaml`) all install from
  the `.lock` files — not the abstract spec — so every environment gets the
  exact same dependency graph.
- **After editing a `requirements*.txt` file, run `make lock` before
  committing.** Nothing currently blocks a commit that edits the `.txt`
  spec without regenerating the lock; this is a known gap (see §7).

---

## 6. Evidence-led PRs / docs & diagrams

- `ARCHITECTURE.md` carries the pipeline diagrams and node-by-node
  contract; `README.md` is the pitch + quickstart; `CHANGELOG.md` is the
  append-only history — each has one job, and none restates the others.
- **Numbers in prose are traced, not typed from memory.** `CLAUDE.md`:
  "never write a number into a doc without tracing it to
  `outputs/summary.json` or a fresh computation" — the [4.7.0] audit is a
  direct example: the "464 tests" figure that was *then* in
  `README.md`/`CONTRIBUTING.md` was `pytest --collect-only`'s actual output
  at that time, not a hand-typed guess, and
  `scripts/check_docs_sync.py` now makes that mechanically true forever
  instead of true-until-the-next-drift.
- **Every agent emits a `DecisionLogger` trace** (`decision_type`, `reason`,
  `evidence`, `confidence`, `alternatives`) that `ExportAgent` writes to
  `outputs/decisions_*.json` — the traceability contract in
  `docs/decision-logging.md`. A PR that adds agent logic without a
  decision-log entry for its new branch is incomplete by this repo's own
  standard.
- **CHANGELOG entries name the audit that found the issue**, not just the
  fix — e.g. `mattpocock-skills:codebase-design` in [4.6.0], this document's
  own audit in [4.7.0] — so a future reader can trace *why* something
  changed, not just *what* changed.

---

## 7. Known gaps (honest, not fixed yet)

- Nothing blocks committing a `requirements*.txt` edit without regenerating
  the matching `.lock` file — `make lock` is manual. A pre-commit hook
  comparing the two would close this.
- `pipeline/analyzer.py` (73%), `hf_loader.py` (63%), and `vector_memory.py`
  (76%) remain below the file-level bar that `graph.py`/`insights_agent.py`
  were just raised to — acceptable for now (see §3) but the next coverage
  pass should target these, particularly `hf_loader.py`'s dataset-streaming
  edge cases.
- `scripts/check_docs_sync.py` checks test-count and version drift (both the
  `pyproject.toml`/`CHANGELOG.md` version and README/ARCHITECTURE "vX.Y"
  banners) only — it does not (yet) check agent-count or model-name
  mentions, the other two drift classes `CLAUDE.md` asks a human/assistant
  to check manually each session.
- **The drift check's real-world sensitivity is limited by small per-batch
  sample sizes.** A real-data check against 28 actual historical runs found
  `fcr_rate_pct`'s baseline standard deviation, at 20-call-batch granularity
  (worsened by a few 3-call smoke-test runs mixed into the same history),
  is large enough that the drift threshold only fires outside roughly
  [24.5%, 113.5%] — effectively never, for a percentage metric. The
  threshold formula (`pipeline/drift.py`) is correctly implemented per
  spec; this is real-world sensitivity, not a bug. Mitigated in [4.8.0]'s
  fix wave by `DRIFT_MIN_CALLS_PER_RUN` (excludes small/noisy runs from
  both the baseline and the current-run verdict), but the proper future
  fix is running the drift check on the full orchestrated ~100-call run
  rather than per-20-call-batch.

---

*Last verified against the actual codebase (not assumed) on 2026-09-25 —
every command in this document was run, not just read, before being
written down here.*
