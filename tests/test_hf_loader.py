"""
Tests for pipeline/hf_loader.py — transcript building and the local-CSV
loading path. The HuggingFace streaming path requires network and is
covered only by its dispatch logic here.
"""

import pandas as pd
import pytest

import pipeline.hf_loader as hf_loader
from pipeline.hf_loader import _build_transcripts, load_telecom_transcripts


def _turns(conv_id: str, n: int, start: str = "2024-01-01 10:00:00") -> list[dict]:
    base = pd.Timestamp(start)
    return [
        {
            "conversation_id": conv_id,
            "speaker":         "agent" if i % 2 == 0 else "client",
            "date_time":       base + pd.Timedelta(seconds=15 * i),
            "text":            f"Turn {i} of conversation {conv_id} with enough text to count.",
        }
        for i in range(n)
    ]


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date_time"] = pd.to_datetime(df["date_time"])
    return df.sort_values(["conversation_id", "date_time"])


# ── _build_transcripts ────────────────────────────────────────────────

class TestBuildTranscripts:
    def test_builds_expected_schema(self):
        df = _frame(_turns("conv-a", 6))
        out = _build_transcripts(df, ["conv-a"])
        assert len(out) == 1
        t = out[0]
        assert t["call_id"] == "conv-a"
        assert t["turn_count"] == 6
        assert t["agent_turns"] == 3
        assert t["customer_turns"] == 3
        assert t["call_date"] == "2024-01-01"
        assert t["raw_start"] == "10:00:00"
        assert t["raw_end"] == "10:01:15"

    def test_speaker_labels_and_timestamps_in_text(self):
        df = _frame(_turns("conv-a", 4))
        text = _build_transcripts(df, ["conv-a"])[0]["transcript_text"]
        lines = text.split("\n")
        assert lines[0].startswith("[10:00:00] AGENT:")
        assert lines[1].startswith("[10:00:15] CUSTOMER:")

    def test_skips_conversations_under_four_turns(self):
        df = _frame(_turns("short", 3) + _turns("long", 5))
        out = _build_transcripts(df, ["short", "long"])
        assert [t["call_id"] for t in out] == ["long"]

    def test_skips_when_too_few_nonempty_lines(self):
        rows = _turns("conv-a", 5)
        for row in rows[:2]:
            row["text"] = ""  # blank turns are dropped from the transcript text
        df = _frame(rows)
        assert _build_transcripts(df, ["conv-a"]) == []

    def test_unknown_id_ignored(self):
        df = _frame(_turns("conv-a", 4))
        assert _build_transcripts(df, ["conv-missing"]) == []


# ── Local CSV path ────────────────────────────────────────────────────

@pytest.fixture
def local_csv(tmp_path, monkeypatch):
    rows = _turns("conv-a", 5) + _turns("conv-b", 6) + _turns("conv-c", 4)
    df = pd.DataFrame(rows)
    df["date_time"] = df["date_time"].astype(str)
    csv_path = tmp_path / "telecom_test.csv"
    df.to_csv(csv_path, index=False)
    monkeypatch.setattr(hf_loader, "LOCAL_CSV_PATH", csv_path)
    return csv_path


class TestLoadFromCsv:
    def test_returns_n_transcripts(self, local_csv):
        out = load_telecom_transcripts(n=2, seed=42, offset=0)
        assert len(out) == 2
        assert all(t["transcript_text"] for t in out)

    def test_reproducible_with_same_seed(self, local_csv):
        run1 = load_telecom_transcripts(n=2, seed=7, offset=0)
        run2 = load_telecom_transcripts(n=2, seed=7, offset=0)
        assert [t["call_id"] for t in run1] == [t["call_id"] for t in run2]

    def test_offset_beyond_data_returns_nothing(self, local_csv):
        # offset is scaled by _BUFFER_X on both bounds (see _select_ids) so
        # that non-overlapping offsets stay disjoint even after shuffling —
        # with only 3 conversations total, any offset beyond the first
        # logical batch has nothing left to slice into.
        out = load_telecom_transcripts(n=5, seed=42, offset=2)
        assert out == []

    def test_dispatches_to_huggingface_when_csv_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hf_loader, "LOCAL_CSV_PATH", tmp_path / "missing.csv")
        called = {}

        def fake_hf(n, seed, offset):
            called.update(n=n, seed=seed, offset=offset)
            return []

        monkeypatch.setattr(hf_loader, "_load_from_huggingface", fake_hf)
        load_telecom_transcripts(n=3, seed=1, offset=10)
        assert called == {"n": 3, "seed": 1, "offset": 10}


# ── Non-overlapping offsets (regression: production bug, see hf_loader.py
# module docstring — a 10-batch run only returned 136/200 unique conversations
# before _select_ids() replaced the overlapping-window sampling) ──────────

@pytest.fixture
def large_local_csv(tmp_path, monkeypatch):
    """700 synthetic conversations — enough for 5 non-overlapping
    offset*_BUFFER_X windows (_BUFFER_X=6) at n=20: the largest offset
    tested (80) needs (80+20)*6=600 IDs available."""
    rows: list[dict] = []
    for i in range(700):
        rows.extend(_turns(f"conv-{i:04d}", 4))
    df = pd.DataFrame(rows)
    df["date_time"] = df["date_time"].astype(str)
    csv_path = tmp_path / "telecom_large.csv"
    df.to_csv(csv_path, index=False)
    monkeypatch.setattr(hf_loader, "LOCAL_CSV_PATH", csv_path)
    return csv_path


class TestNonOverlappingOffsets:
    def test_consecutive_offsets_are_disjoint(self, large_local_csv):
        batch1 = load_telecom_transcripts(n=20, seed=42, offset=0)
        batch2 = load_telecom_transcripts(n=20, seed=42, offset=20)
        ids1 = {t["call_id"] for t in batch1}
        ids2 = {t["call_id"] for t in batch2}
        assert len(ids1) == 20
        assert len(ids2) == 20
        assert ids1.isdisjoint(ids2)

    def test_ten_batch_run_has_zero_duplicate_ids(self, large_local_csv):
        # Mirrors the actual production scenario: run_batches.py issuing
        # offsets 0, 20, 40, ... for a multi-batch run.
        seen: set[str] = set()
        for i in range(5):  # 5*20=100 conversations, well within the 150 available
            batch = load_telecom_transcripts(n=20, seed=42, offset=i * 20)
            ids = {t["call_id"] for t in batch}
            assert ids.isdisjoint(seen), f"batch offset={i * 20} overlapped an earlier batch"
            seen |= ids
        assert len(seen) == 100

    def test_same_offset_is_reproducible(self, large_local_csv):
        run1 = load_telecom_transcripts(n=20, seed=42, offset=40)
        run2 = load_telecom_transcripts(n=20, seed=42, offset=40)
        assert [t["call_id"] for t in run1] == [t["call_id"] for t in run2]
