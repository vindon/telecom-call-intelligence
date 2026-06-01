# Security Policy

## Scope

This policy covers the Telecom Call Intelligence pipeline and its supporting infrastructure. The system is a multi-agent AI pipeline that processes call transcript data using Claude (Anthropic), NVIDIA NIM, and Gemini (Google) APIs.

---

## Sensitive Data Handling

| Data type | Handling |
|-----------|----------|
| `ANTHROPIC_API_KEY` | Stored in `.env` only — never logged, never committed, `SecretGuard` redacts `sk-ant-*` patterns from all LLM outputs, state serialisation, and log messages |
| `GEMINI_API_KEY` | Stored in `.env` only — `SecretGuard` redacts `AIza*` patterns from all outputs and logs |
| `NVIDIA_API_KEY` | Stored in `.env` only — `SecretGuard` redacts `nvapi-*` patterns; also caught by env-var pattern guard |
| Call transcript text | Scanned by `PIIScanner` before any LLM call; 6 PII pattern types detected and redacted to `[REDACTED]`; never stored in decision log evidence fields |
| `outputs/agent_memory.json` | Contains aggregated KPIs and run history only — no raw transcripts or PII |
| `outputs/decisions_{ts}.json` | Agent reasoning records — evidence fields contain only scores/counts/flags, never transcript text |
| `outputs/audit_log_{ts}.json` | Agent events and governance decisions — no transcript text |
| GitHub Secrets | API keys stored as encrypted repo secrets for CI; never appear in logs or artifact outputs |

---

## PII Protection

The `PIIScanner` in `pipeline/governance.py` runs on every transcript **before** it is sent to any LLM. Patterns detected and redacted:

- US phone numbers (`phone_us`)
- Social security numbers (`ssn`)
- Email addresses (`email`)
- Credit card numbers (`credit_card`)
- Dates of birth (`dob`)
- Account numbers (`account_num`)

The telecom corpus (`talkmap/telecom-conversation-corpus`) is synthetic and anonymised. The scanner is a defence-in-depth measure for production datasets containing real customer data.

**Decision log protection:** `DecisionLogger` captures only quantitative evidence (scores, counts, boolean flags) — never transcript text, customer names, or any PII. The `evidence` dict design is enforced by code review convention.

---

## API Key Security

- `.env` is listed in `.gitignore` and must never be committed
- The pre-commit hook `detect-private-key` blocks accidental key commits
- Keys are never printed, logged, or included in error messages
- `SecretGuard.redact_for_log()` is called before any log message that might contain key material
- `SecretGuard.assert_no_secrets_in_output()` is called on every raw LLM response before JSON parsing
- Startup validation (`run_pipeline.py`) checks for the correct key based on `EXTRACTION_MODEL` — failure exits immediately with guidance, not a traceback

**If a key is accidentally exposed:**
- Anthropic: rotate immediately at [console.anthropic.com](https://console.anthropic.com)
- Google: rotate at [aistudio.google.com](https://aistudio.google.com)
- NVIDIA: rotate at [build.nvidia.com](https://build.nvidia.com)
- Then: remove from git history (`git filter-branch` or `git-secrets`)

---

## Threat Model

| Threat | Mitigation |
|--------|------------|
| API key leakage via git | `.gitignore`, pre-commit `detect-private-key`, GitHub secret scanning, `SecretGuard` patterns for Anthropic + Google + OpenAI + NVIDIA + JWT + Bearer |
| Prompt injection in transcript data | `InputSanitizer`: 10 regex patterns covering DAN mode, jailbreak, XML role injection, Llama template injection, instruction override; neutralise to `[FILTERED]` (not reject — prevents DoS from single bad record) |
| Token bomb (DoS via oversized input) | `InputSanitizer`: hard cap at 50,000 chars; truncate with `[TRUNCATED-SECURITY]` marker |
| PII in LLM prompts | `PIIScanner` redacts before every API call; `AuditLog` records detections |
| Code execution via LLM output | `OutputSanitizer`: `__import__`, `eval`, `exec`, `subprocess`, XSS patterns → `[CONTENT_FILTERED]` |
| Secret leakage via LLM output | `SecretGuard.assert_no_secrets_in_output()` on every raw LLM response |
| Cross-agent tool hijacking | `AgentScopeGuard`: per-agent authorised tool set; violation raises `SecurityViolation` before invocation |
| Response bomb (32KB+ LLM output) | `OutputSanitizer.check_response_size()`: hard cap at 32,768 bytes |
| Runaway API cost (ReAct loops) | `BudgetGuard` (hard-stop at `BUDGET_USD` from `config.py`); `CLAUDE_RATE_LIMITER` (50/60s); `GEMINI_RATE_LIMITER` (15/60s) |
| Corrupt extraction data reaching aggregation | `QualityGate` blocks pipeline at < `MIN_PASS_RATE` QA pass rate |
| Upstream corpus injection | HuggingFace streaming is read-only; every transcript validated and sanitised before use |
| State tampering between agents | `InputSanitizer.validate_state_schema()` checks required keys at each agent boundary |
| Path traversal in export | `ExportAgent` writes only to `OUTPUT_DIR`; no user-controlled path components |
| Dependency compromise | Pinned `>=` ranges in `requirements.txt`; `pip audit` recommended pre-release |

---

## Reporting a Vulnerability

To report a security vulnerability:

1. **Do not open a public GitHub issue**
2. Email **vinoth.n@outlook.com** with subject: `[SECURITY] Telecom Call Intelligence`
3. Include: description, reproduction steps, potential impact, and suggested fix if known
4. You will receive a response within 48 hours
5. Agreed-upon fixes will be released within 7 days of confirmation

We appreciate responsible disclosure and will acknowledge your contribution.
