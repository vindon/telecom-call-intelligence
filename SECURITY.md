# Security Policy

## Scope

This policy covers the Telecom Call Intelligence pipeline and its supporting infrastructure.

---

## Sensitive Data Handling

| Data type | Handling |
|-----------|----------|
| `GEMINI_API_KEY` | Stored in `.env` only — never logged, never committed, never transmitted outside Google AI Studio API calls |
| Call transcript text | Scanned by `PIIScanner` before any LLM call; 6 PII pattern types detected and redacted to `[REDACTED]` |
| `outputs/agent_memory.json` | Contains aggregated KPIs and run history — no raw transcripts or PII |
| Audit log (`audit_log_*.json`) | Records agent actions and governance decisions — no transcript text |
| GitHub Secrets | `GEMINI_API_KEY` stored as an encrypted repo secret for CI; never appears in logs |

---

## PII Protection

The `PIIScanner` in `pipeline/governance.py` runs on every transcript **before** it is sent to the LLM. Patterns detected and redacted:

- US phone numbers (`phone_us`)
- Social security numbers (`ssn`)
- Email addresses (`email`)
- Credit card numbers (`credit_card`)
- Dates of birth (`dob`)
- Account numbers (`account_num`)

The telecom corpus (`talkmap/telecom-conversation-corpus`) is synthetic and anonymised. The scanner is a defence-in-depth measure for custom datasets.

---

## API Key Security

- `.env` is listed in `.gitignore` and must never be committed
- The pre-commit hook `detect-private-key` blocks accidental key commits
- Keys are never printed, logged, or included in error messages
- If a key is accidentally exposed, rotate it immediately at [aistudio.google.com](https://aistudio.google.com) and invalidate the old key

---

## Reporting a Vulnerability

To report a security vulnerability:

1. **Do not open a public GitHub issue**
2. Email **vinoth.n@outlook.com** with subject: `[SECURITY] Telecom Call Intelligence`
3. Include: description, reproduction steps, potential impact, and suggested fix if known
4. You will receive a response within 48 hours
5. Agreed-upon fixes will be released within 7 days of confirmation

We appreciate responsible disclosure and will acknowledge your contribution.

---

## Threat Model

| Threat | Mitigation |
|--------|------------|
| API key leakage via git | `.gitignore`, pre-commit `detect-private-key`, GitHub secret scanning |
| PII in LLM prompts | PIIScanner redacts before every API call; audit log records detections |
| Runaway API cost | `BudgetGuard` hard-stops at $5.00 USD per run |
| Corrupt extraction data reaching aggregation | `QualityGate` blocks pipeline at <40% QA pass rate |
| Upstream corpus injection | HuggingFace streaming is read-only; transcripts are validated before use |
| Dependency compromise | Pinned `>=` ranges in `requirements.txt`; `pip audit` recommended pre-release |
