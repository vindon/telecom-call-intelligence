"""
scripts/build_golden_set.py — one-time (or occasional) builder for
evals/golden_set.json.

Run manually when the golden set needs refreshing — e.g. after a
deliberate prompt/schema change where the old golden values are no
longer the right target. Never run automatically; this is a curation
tool, not part of any regular pipeline or CI step.

Usage:
    .venv/bin/python scripts/build_golden_set.py \\
        --source outputs/full_results_combined_20260809_175823.json \\
        --n 15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pipeline.analyzer import _CRITICAL_FIELDS as EXTRACTION_CRITICAL_FIELDS
from pipeline.config import LOCAL_CSV_PATH
from pipeline.hf_loader import _build_transcripts

OUTPUT_PATH = Path("evals/golden_set.json")


def select_golden_cases(records: list[dict], n: int = 15) -> list[dict]:
    """
    Pick up to `n` records that are HIGH-QA-graded and passed the Data
    Quality Gate, round-robin across distinct issue_1_category values so
    no single category dominates the set.

    `records` are full per-call dicts as written to
    outputs/full_results_*.json — each already carries `_qa_grade` and
    `_dq_gate_passed` (written by QualityAgent during the original run;
    see qa_audit.check_data_quality()).
    """
    eligible = [
        r for r in records if r.get("_qa_grade") == "HIGH" and r.get("_dq_gate_passed") is True
    ]

    by_category: dict[str, list[dict]] = {}
    for r in eligible:
        category = r.get("issue_1_category") or "unknown"
        by_category.setdefault(category, []).append(r)

    selected: list[dict] = []
    categories = list(by_category.keys())
    idx = 0
    while len(selected) < n and any(by_category.values()):
        cat = categories[idx % len(categories)]
        bucket = by_category[cat]
        if bucket:
            selected.append(bucket.pop(0))
        idx += 1

    return selected[:n]


def build_case(record: dict, transcript: dict) -> dict:
    """Convert one selected record + its rebuilt transcript into a golden_set.json case."""
    return {
        "call_id": record["call_id"],
        "transcript_text": transcript["transcript_text"],
        "call_date": transcript.get("call_date", ""),
        "expected": {f: record.get(f) for f in EXTRACTION_CRITICAL_FIELDS},
        "expected_qa_grade": record.get("_qa_grade", "HIGH"),
    }


def _load_transcripts_for_call_ids(call_ids: list[str]) -> dict[str, dict]:
    """
    Rebuild transcript_text for specific call_ids, using the exact same CSV
    parsing pipeline.hf_loader._load_from_csv uses — so the golden set's
    frozen transcript matches what the pipeline itself would produce, not a
    second, independently-written reconstruction that could subtly diverge.
    """
    df = pd.read_csv(
        LOCAL_CSV_PATH,
        dtype={"conversation_id": str, "speaker": str, "text": str},
    )
    df_sel = df[df["conversation_id"].isin(call_ids)].copy()
    df_sel["date_time"] = pd.to_datetime(df_sel["date_time"], format="mixed", errors="coerce")
    df_sel = df_sel.dropna(subset=["date_time"])
    df_sel = df_sel.sort_values(["conversation_id", "date_time"])
    transcripts = _build_transcripts(df_sel, call_ids)
    return {t["call_id"]: t for t in transcripts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evals/golden_set.json")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="A past outputs/full_results*.json run to select HIGH-QA/DQ-passed cases from",
    )
    parser.add_argument("--n", type=int, default=15, help="Number of golden cases to select")
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    records = json.loads(args.source.read_text())
    selected = select_golden_cases(records, n=args.n)
    if len(selected) < args.n:
        print(
            f"⚠ Only found {len(selected)}/{args.n} eligible (HIGH-QA + DQ-gate-passed) "
            f"records in {args.source} — consider a larger/different --source"
        )

    call_ids = [r["call_id"] for r in selected]
    transcripts_by_id = _load_transcripts_for_call_ids(call_ids)

    cases = []
    for record in selected:
        transcript = transcripts_by_id.get(record["call_id"])
        if transcript is None:
            print(f"⚠ Skipping {record['call_id'][:12]} — transcript not found in {LOCAL_CSV_PATH}")
            continue
        cases.append(build_case(record, transcript))

    print(f"\nSelected {len(cases)} golden cases:")
    for c in cases:
        excerpt = c["transcript_text"][:80].replace("\n", " ")
        print(f"  {c['call_id'][:12]}  [{c['expected']['issue_1_category']}]  {excerpt}...")

    payload = {
        "frozen_from": str(args.source),
        "cases": cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2))
    print(f"\n✓ Wrote {len(cases)} cases → {args.out}")


if __name__ == "__main__":
    main()
