#!/usr/bin/env python3
"""
check_docs_sync.py — fail fast on the exact doc-drift this repo has hit twice
------------------------------------------------------------------------------
Verified by hand during the 2026-09-25 engineering-standards audit: pyproject.toml
was at 4.1.1 while CHANGELOG.md's top entry was 4.6.0, and README.md/CONTRIBUTING.md
each quoted a different, stale test count (399 and 342, vs. 432 actually passing).
CLAUDE.md already told Claude to check for exactly this at the end of every
session — a manual reminder that drifted anyway, twice, per CHANGELOG.md's own
history. This script makes it a CI/pre-commit gate instead of a habit.

Checks:
  1. pyproject.toml's version == the top [X.Y.Z] heading in CHANGELOG.md
  2. every "<N> tests"/"<N> unit tests"/badge test-count mention in README.md,
     CONTRIBUTING.md, and CLAUDE.md == the number of tests pytest actually
     collects
  3. every "vX.Y" pipeline-version banner in README.md/ARCHITECTURE.md matches
     pyproject.toml's major.minor (banners omit the patch component)
  4. CLAUDE.md's own hyphenated ("<N>-test suite") and pytest-output-style
     ("<N> passed") count mentions also match — added after CLAUDE.md was
     found still saying "399-test suite"/"**399 passed**" during the
     2026-09-25 drift/eval audit, phrasings the original BADGE_RE/COUNT_RE
     didn't match
  5. `pipeline/agents/export_agent.py`'s hardcoded `"pipeline_version"`
     manifest literal matches pyproject.toml's version — added after that
     literal was found stale (still "4.5.0" after a 4.7.0 bump) in the same
     audit

Deliberately does NOT touch CHANGELOG.md's body — historical entries
("Net: 399 tests (was 404...)") are a record of the past, not a claim about
the current state, and must never be "corrected" to match today's count.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOCS_TO_CHECK = ["README.md", "CONTRIBUTING.md", "CLAUDE.md"]
VERSION_BANNER_DOCS = ["README.md", "ARCHITECTURE.md"]

BADGE_RE = re.compile(r"Tests-(\d+)%20passing")
COUNT_RE = re.compile(r"\b(\d{2,4})(?:%20| )(?:unit )?tests?\b", re.IGNORECASE)
HYPHEN_COUNT_RE = re.compile(r"\b(\d{2,4})-tests?\b", re.IGNORECASE)
PASSED_RE = re.compile(r"\b(\d{2,4}) passed\b")
VERSION_BANNER_RE = re.compile(r"\bv(\d+\.\d+)\b")


def _pyproject_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if not m:
        raise RuntimeError('pyproject.toml: could not find a `version = "..."` line')
    return m.group(1)


def check_version_sync(pyproject_version: str) -> list[str]:
    errors = []
    changelog = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"^##\s*\[([^\]]+)\]", changelog, re.MULTILINE)
    if not m:
        return ["CHANGELOG.md: could not find a `## [X.Y.Z]` heading"]
    changelog_version = m.group(1)

    if pyproject_version != changelog_version:
        errors.append(
            f"Version mismatch: pyproject.toml says {pyproject_version!r}, "
            f"but CHANGELOG.md's top entry is {changelog_version!r}. "
            f"Bump pyproject.toml to match, or add a new CHANGELOG.md entry."
        )
    return errors


def check_version_banner_sync(pyproject_version: str) -> list[str]:
    """README.md/ARCHITECTURE.md banners say 'vX.Y' (no patch component)."""
    errors = []
    major_minor = ".".join(pyproject_version.split(".")[:2])
    for doc_name in VERSION_BANNER_DOCS:
        path = ROOT / doc_name
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            for m in VERSION_BANNER_RE.finditer(line):
                if m.group(1) != major_minor:
                    errors.append(
                        f"{doc_name}:{lineno}: banner says v{m.group(1)}, but "
                        f"pyproject.toml is {pyproject_version!r} (v{major_minor}): "
                        f"{line.strip()!r}"
                    )
    return errors


def live_test_count() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-m",
            "not slow and not integration",
            "--collect-only",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    m = re.search(r"(\d+) tests? collected", result.stdout)
    if not m:
        print(result.stdout[-2000:], file=sys.stderr)
        raise RuntimeError("Could not parse test count from pytest --collect-only output")
    return int(m.group(1))


def check_test_count_sync(actual: int) -> list[str]:
    errors = []
    for doc_name in DOCS_TO_CHECK:
        path = ROOT / doc_name
        if not path.exists():
            continue
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in (
                list(BADGE_RE.finditer(line))
                + list(COUNT_RE.finditer(line))
                + list(HYPHEN_COUNT_RE.finditer(line))
                + list(PASSED_RE.finditer(line))
            ):
                claimed = int(m.group(1))
                if claimed != actual:
                    errors.append(
                        f"{doc_name}:{lineno}: claims {claimed} tests, "
                        f"but pytest currently collects {actual}: {line.strip()!r}"
                    )
    return errors


def check_export_agent_version_sync(pyproject_version: str) -> list[str]:
    """pipeline/agents/export_agent.py hardcodes 'pipeline_version' into
    run_manifest_*.json — was already stale once (found during the
    2026-09-25 drift/eval audit) before check_docs_sync.py could catch it."""
    errors = []
    path = ROOT / "pipeline" / "agents" / "export_agent.py"
    text = path.read_text()
    m = re.search(r'"pipeline_version":\s*"([^"]+)"', text)
    if not m:
        return [f'{path}: could not find a `"pipeline_version": "..."` line']
    if m.group(1) != pyproject_version:
        errors.append(
            f"pipeline/agents/export_agent.py: pipeline_version literal is "
            f"{m.group(1)!r}, but pyproject.toml is {pyproject_version!r}"
        )
    return errors


def main() -> int:
    pyproject_version = _pyproject_version()
    errors = check_version_sync(pyproject_version)
    errors += check_version_banner_sync(pyproject_version)
    actual = live_test_count()
    errors += check_test_count_sync(actual)
    errors += check_export_agent_version_sync(pyproject_version)

    if errors:
        print("check_docs_sync: FAILED\n")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nUpdate the stale doc(s) above (or CHANGELOG.md, for the version "
            "check) so they match the current, actual state."
        )
        return 1

    print(f"check_docs_sync: OK — version and test count ({actual}) are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
