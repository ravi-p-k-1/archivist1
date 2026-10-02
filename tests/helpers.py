"""Shared test fixtures for the JSON transcript pipeline tests."""

import copy
import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample-meeting.json"
FIXTURE_DATE = "2025-06-15"


def load_fixture() -> dict:
    """Return a fresh, mutable copy of the synthetic sample meeting."""

    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def write_transcript(root: Path, meeting_date: str, payload: dict) -> Path:
    """Write a transcript payload to transcripts/<date>/meet/transcript.json."""

    destination = root / "transcripts" / meeting_date / "meet" / "transcript.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload), encoding="utf-8")
    return destination
