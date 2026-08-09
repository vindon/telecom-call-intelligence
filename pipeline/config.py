"""
pipeline/config.py  —  Central Configuration
----------------------------------------------
Single source of truth for all pipeline constants. Every module that
previously defined MODEL, MAX_TOKENS, OUTPUT_DIR, etc. inline should
import from here instead.

Groupings mirror the system architecture:
  Model       — LLM API parameters (Claude, NVIDIA NIM, Gemini fallback)
  API         — Retry and rate-limit settings
  Batching    — Default CLI argument values
  Paths       — Filesystem locations
  Governance  — Budget and quality thresholds
  Validation  — Transcript acceptance criteria
  QA          — Scoring thresholds and history limits
"""

from pathlib import Path

# ── Model ──────────────────────────────────────────────────────────────
# Free-tier limits (2026-05): gemini-2.5-flash-lite = 500 RPD / 15 RPM.
# gemini-2.0-flash-lite = 1 500 RPD / 30 RPM (separate quota pool).
# Claude Haiku is the primary extraction model; Gemini is fallback if ANTHROPIC_API_KEY absent.
EXTRACTION_MODEL       = "claude-haiku-4-5-20251001"

# InsightsAgent primary provider: NVIDIA NIM (OpenAI-compatible API).
# Llama 3.3 70B Instruct gives strong reasoning and reliable JSON output
# via response_format=json_object. Fallback chain: NIM → Claude → rule-based.
INSIGHTS_MODEL         = "meta/llama-3.3-70b-instruct"
NVIDIA_BASE_URL        = "https://integrate.api.nvidia.com/v1"
MAX_OUTPUT_TOKENS      = 8192
EXTRACTION_TEMPERATURE = 0.1   # near-deterministic for structured extraction
INSIGHTS_TEMPERATURE   = 0.3   # slightly creative for strategic recommendations

# ── API ────────────────────────────────────────────────────────────────
MAX_RETRIES_PER_CALL = 3
RETRY_DELAYS_S       = (30, 60, 120)   # exponential backoff on 429

# No Anthropic/OpenAI/Gemini client in this codebase used to set an explicit
# timeout, so every one defaulted to its SDK's 600s read timeout — the same
# order of magnitude as Orchestrator's 600s per-batch subprocess timeout.
# A slow/unresponsive provider (observed: NVIDIA NIM) could hang right up to
# that limit, causing the whole batch subprocess to be killed and retried
# from scratch — discarding already-successful extraction work. Every LLM
# client construction must pass one of these explicitly.
EXTRACTION_API_TIMEOUT_S = 60   # Claude Haiku / Gemini — observed calls take 15-25s
INSIGHTS_API_TIMEOUT_S   = 45   # NVIDIA NIM / Claude fallback — fail fast into the next tier

# ── Batching ───────────────────────────────────────────────────────────
# With gemini-2.5-flash-lite free tier (20 RPD), use DEFAULT_BATCH_SIZE=20
# and one batch per day. Switch to 2.0-flash-lite for multi-batch runs.
DEFAULT_N_CALLS        = 100
DEFAULT_BATCH_SIZE     = 20
DEFAULT_SEED           = 42
DEFAULT_DELAY_S        = 2.0
DEFAULT_RATE_LIMIT_RPM = 15
# No DEFAULT_MAX_RETRIES: Orchestrator halts on the first batch failure and
# requires explicit human review (run_batches.py --acknowledge-halt) instead
# of auto-retrying — see pipeline/orchestrator.py's strict failure policy.

# ── Paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR  = Path("outputs")
MEMORY_PATH = OUTPUT_DIR / "agent_memory.json"
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
HF_DATASET      = "talkmap/telecom-conversation-corpus"
LOCAL_CSV_PATH  = Path("telecom_200k.csv")   # auto-detected; falls back to HF if absent

# ── Governance ─────────────────────────────────────────────────────────
# Budget hard-stop per run.
# Claude Haiku pricing ($0.80 in / $4.00 out per MTok):
#   ~2 000 prompt + ~1 500 output tokens per call → ≈$0.0076/call
#   $5.00 ≈ 650 calls.  Raise to $25.00 for production 1 000-call batches.
# Gemini 2.0/2.5 Flash Lite ($0.10 in / $0.40 out per MTok):
#   same token volumes → ≈$0.0008/call.  $5.00 ≈ 6 000 calls.
BUDGET_USD         = 5.00   # hard-stop per run — adjust per model and batch size
MIN_PASS_RATE      = 0.40   # catastrophic quality gate threshold (40%)
QUALITY_WARN_RATE  = 0.70   # warning threshold — logs prominently but does not stop pipeline

# ── Data validation ────────────────────────────────────────────────────
MIN_TRANSCRIPT_CHARS = 150
MIN_TURN_COUNT       = 4

# ── Data quality gate (AHT / timestamp integrity) ──────────────────────
# Tolerance for summing phase durations vs. total_duration_seconds. Both are
# LLM-read-off-transcript values, not measured — this absorbs rounding, not
# genuine overcounting. See qa_audit.check_phase_reconciliation().
PHASE_RECONCILIATION_TOLERANCE_S   = 5.0
PHASE_RECONCILIATION_TOLERANCE_PCT = 0.03
# Tolerance for total_duration_seconds vs. raw_duration_seconds (ground-truth
# span from the source dataset's own turn timestamps). Wider than the phase
# tolerance because raw turn timestamps don't capture true hold/silence time,
# so some divergence from the LLM's narrative-paced total is expected.
TIMESTAMP_GROUND_TRUTH_TOLERANCE_S   = 30.0
TIMESTAMP_GROUND_TRUTH_TOLERANCE_PCT = 0.10

# ── QA scoring ─────────────────────────────────────────────────────────
QA_HIGH_THRESHOLD  = 85   # ≥85 → HIGH grade (production-ready)
QA_PASS_THRESHOLD  = 60   # ≥60 → MEDIUM grade (usable)
RUN_HISTORY_LIMIT  = 50   # max runs kept in agent memory

# ── ReAct / agentic control loops ─────────────────────────────────────
REACT_MAX_ITERATIONS     = 2     # extra Reason→Act→Observe cycles per extraction
REACT_QUALITY_THRESHOLD  = 70   # trigger re-query if field-coverage score < this

# ── InsightsAgent deliberation ─────────────────────────────────────────
DELIBERATION_ENABLED     = True  # Analyze → Critique → Synthesize passes

# ── InsightsAgent Claude fallback ─────────────────────────────────────
CLAUDE_INSIGHTS_MODEL    = "claude-haiku-4-5-20251001"  # fallback if NVIDIA unavailable

# ── Human approval gate ────────────────────────────────────────────────
REQUIRE_HUMAN_APPROVAL   = False  # pause before export for explicit human sign-off
APPROVAL_TIMEOUT_S       = 60    # seconds before auto-approve (0 = block indefinitely)

# ── Observability / tracing ────────────────────────────────────────────
LANGSMITH_PROJECT        = "telecom-call-intelligence"

# ── Vector memory ─────────────────────────────────────────────────────
VECTOR_MEMORY_ENABLED    = True
VECTOR_MEMORY_PATH       = OUTPUT_DIR / "vector_memory"
VECTOR_MEMORY_TOP_K      = 3    # top-K similar historical runs to retrieve

# ── Security ──────────────────────────────────────────────────────────
MAX_TRANSCRIPT_CHARS     = 50_000  # hard cap; beyond this is suspicious
MAX_FIELD_STRING_LEN     = 2_000   # per-field string limit in LLM output
MAX_RESPONSE_BYTES       = 32_768  # max LLM JSON response size (32 KB)
