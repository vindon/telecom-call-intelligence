---
name: batch-run
description: Pre-flight quota check and guided production batch run — verifies model quota, optionally switches model, then runs smoke test or full 5×20 batch
---

The user wants to run the telecom pipeline.

**Step 1 — Read current config**

Read `pipeline/config.py` and extract:
- `EXTRACTION_MODEL`
- `DEFAULT_BATCH_SIZE`
- `DEFAULT_N_CALLS`

**Step 2 — Quota reminder**

Print the active model's free-tier limits:
- `gemini-2.5-flash-lite` → 20 RPD / 15 RPM → safe for exactly 1 batch of 20 calls per day; quota resets midnight Pacific
- `gemini-2.0-flash-lite` → 1500 RPD / 30 RPM → safe for the full 5×20 run

**Step 3 — Ask the user**

Ask: "Smoke test (3 calls) or full run (5×20 = 100 calls)?"

If they choose full run AND the active model is `gemini-2.5-flash-lite`:
- Warn: "gemini-2.5-flash-lite has a 20 RPD limit. A 100-call run will exhaust the daily quota after the first batch."
- Ask: "Switch to gemini-2.0-flash-lite in config.py first, or proceed anyway with just one batch?"
- If they want to switch: update both `EXTRACTION_MODEL` and `INSIGHTS_MODEL` in `pipeline/config.py`

**Step 4 — Run**

- Smoke test → `make run`
- Full run → `make run-batches`

**Step 5 — Report**

After the run completes, show:
- The last 10 lines of terminal output
- Files created in `outputs/` since the run started (`ls -lt outputs/ | head -15`)
- Any QA pass rate or cost summary from the output JSON if available
