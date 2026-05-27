"""
pipeline/config.py  —  Central Configuration
----------------------------------------------
Single source of truth for all pipeline constants. Every module that
previously defined MODEL, MAX_TOKENS, OUTPUT_DIR, etc. inline should
import from here instead.

Groupings mirror the system architecture:
  Model       — Gemini API parameters
  API         — Retry and rate-limit settings
  Batching    — Default CLI argument values
  Paths       — Filesystem locations
  Governance  — Budget and quality thresholds
  Validation  — Transcript acceptance criteria
  QA          — Scoring thresholds and history limits
"""

from pathlib import Path

# ── Model ──────────────────────────────────────────────────────────────
# Free-tier limits (2026-05): gemini-2.5-flash-lite = 20 RPD / 15 RPM.
# Switch to gemini-2.0-flash-lite (1 500 RPD / 30 RPM) for larger batch runs.
EXTRACTION_MODEL       = "gemini-2.0-flash-lite"
INSIGHTS_MODEL         = "gemini-2.0-flash-lite"
MAX_OUTPUT_TOKENS      = 8192
EXTRACTION_TEMPERATURE = 0.1   # near-deterministic for structured extraction
INSIGHTS_TEMPERATURE   = 0.3   # slightly creative for strategic recommendations

# ── API ────────────────────────────────────────────────────────────────
MAX_RETRIES_PER_CALL = 3
RETRY_DELAYS_S       = (30, 60, 120)   # exponential backoff on 429

# ── Batching ───────────────────────────────────────────────────────────
# With gemini-2.5-flash-lite free tier (20 RPD), use DEFAULT_BATCH_SIZE=20
# and one batch per day. Switch to 2.0-flash-lite for multi-batch runs.
DEFAULT_N_CALLS        = 100
DEFAULT_BATCH_SIZE     = 20
DEFAULT_SEED           = 42
DEFAULT_DELAY_S        = 2.0
DEFAULT_RATE_LIMIT_RPM = 15
DEFAULT_MAX_RETRIES    = 2

# ── Paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR  = Path("outputs")
MEMORY_PATH = OUTPUT_DIR / "agent_memory.json"
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
HF_DATASET      = "talkmap/telecom-conversation-corpus"
LOCAL_CSV_PATH  = Path("telecom_200k.csv")   # auto-detected; falls back to HF if absent

# ── Governance ─────────────────────────────────────────────────────────
BUDGET_USD    = 5.00   # hard-stop per run
MIN_PASS_RATE = 0.40   # catastrophic quality gate threshold (40%)

# ── Data validation ────────────────────────────────────────────────────
MIN_TRANSCRIPT_CHARS = 150
MIN_TURN_COUNT       = 4

# ── QA scoring ─────────────────────────────────────────────────────────
QA_HIGH_THRESHOLD  = 85   # ≥85 → HIGH grade (production-ready)
QA_PASS_THRESHOLD  = 60   # ≥60 → MEDIUM grade (usable)
RUN_HISTORY_LIMIT  = 50   # max runs kept in agent memory

# ── ReAct / agentic control loops ─────────────────────────────────────
REACT_MAX_ITERATIONS     = 2     # extra Reason→Act→Observe cycles per extraction
REACT_QUALITY_THRESHOLD  = 70   # trigger re-query if field-coverage score < this

# ── InsightsAgent deliberation ─────────────────────────────────────────
DELIBERATION_ENABLED     = True  # Analyze → Critique → Synthesize passes

# ── Parallel extraction ────────────────────────────────────────────────
MAX_CONCURRENT_EXTRACTIONS = 1   # 1 = serial (free-tier safe); raise on paid tier

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
