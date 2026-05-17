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
EXTRACTION_MODEL       = "gemini-2.5-flash-lite"
INSIGHTS_MODEL         = "gemini-2.5-flash-lite"
MAX_OUTPUT_TOKENS      = 8192
EXTRACTION_TEMPERATURE = 0.1   # near-deterministic for structured extraction
INSIGHTS_TEMPERATURE   = 0.3   # slightly creative for strategic recommendations

# ── API ────────────────────────────────────────────────────────────────
MAX_RETRIES_PER_CALL = 3
RETRY_DELAYS_S       = (30, 60, 120)   # exponential backoff on 429

# ── Batching ───────────────────────────────────────────────────────────
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
HF_DATASET  = "talkmap/telecom-conversation-corpus"

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
