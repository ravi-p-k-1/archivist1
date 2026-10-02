"""Loading and validating the TranscripTonic JSON transcript contract.

Path contract: transcripts/<YYYY-MM-DD>/meet/transcript.json. One pending
transcript per run. Entries are numbered e1..eN in transcript order; each
entry's time is reported as elapsed HH:MM:SS from the meeting's start,
since that's what the compact view and evidence lookups key off of.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MEETING_TIMEZONE = ZoneInfo("America/Los_Angeles")
SOURCE_NAME = "meet"


class ProcessingError(RuntimeError):
    """A safe, user-facing processing error."""


@dataclass(frozen=True)
class Entry:
    id: str
    speaker: str
    elapsed: str
    text: str


@dataclass(frozen=True)
class Transcript:
    entries: list[Entry]
    meeting_date: str
    source_path: Path
    by_id: dict[str, Entry] = field(default_factory=dict)


def _parse_timestamp(value: object, context: str) -> datetime:
    if not isinstance(value, str):
        raise ProcessingError(f"{context} must be an ISO 8601 timestamp.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProcessingError(f"{context} must be an ISO 8601 timestamp.") from exc


def _format_elapsed(entry_time: datetime, start_time: datetime) -> str:
    total_seconds = max(0, int((entry_time - start_time).total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _find_pending_transcript(root: Path) -> Path:
    candidates = sorted((root / "transcripts").glob("*/meet/transcript.json"))
    if not candidates:
        raise ProcessingError(
            "No pending transcript found under transcripts/<date>/meet/transcript.json."
        )
    if len(candidates) > 1:
        raise ProcessingError("Only one pending transcript is supported per run.")
    return candidates[0]


def load_pending_transcript(root: Path) -> Transcript:
    """Find, validate, and parse the single pending transcript under transcripts/."""

    root = root.resolve()
    source = _find_pending_transcript(root)
    meeting_date = source.relative_to(root).parts[1]

    try:
        parsed_date = date.fromisoformat(meeting_date)
    except ValueError as exc:
        raise ProcessingError("Transcript date must use YYYY-MM-DD.") from exc
    if parsed_date.isoformat() != meeting_date:
        raise ProcessingError("Transcript date must use YYYY-MM-DD.")

    archive_path = root / "archived" / meeting_date / SOURCE_NAME / "transcript.json"
    if archive_path.exists():
        raise ProcessingError(f"Archive destination already exists: {archive_path}")

    try:
        raw_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProcessingError("Transcript could not be read as UTF-8 text.") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ProcessingError("Transcript is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ProcessingError("Transcript JSON must be an object.")
    if payload.get("webhookBodyType") != "advanced":
        raise ProcessingError('Transcript webhookBodyType must be "advanced".')

    entries_raw = payload.get("transcript")
    if not isinstance(entries_raw, list) or not entries_raw:
        raise ProcessingError("Transcript must have a non-empty transcript list.")

    start_time = _parse_timestamp(payload.get("meetingStartTimestamp"), "meetingStartTimestamp")
    end_time = _parse_timestamp(payload.get("meetingEndTimestamp"), "meetingEndTimestamp")
    if end_time < start_time:
        raise ProcessingError("meetingEndTimestamp must not be before meetingStartTimestamp.")

    expected_date = start_time.astimezone(MEETING_TIMEZONE).date().isoformat()
    if expected_date != meeting_date:
        raise ProcessingError(
            f"Folder date {meeting_date} does not match the meeting start time "
            f"in America/Los_Angeles ({expected_date})."
        )

    entries: list[Entry] = []
    for index, raw_entry in enumerate(entries_raw, start=1):
        if not isinstance(raw_entry, dict):
            raise ProcessingError(f"Transcript entry {index} must be an object.")
        try:
            person_name = raw_entry["personName"]
            timestamp_value = raw_entry["timestamp"]
            text = raw_entry["transcriptText"]
        except KeyError as exc:
            raise ProcessingError(f"Transcript entry {index} is missing {exc.args[0]}.") from exc
        if not isinstance(person_name, str) or not person_name.strip():
            raise ProcessingError(f"Transcript entry {index} has an empty personName.")
        if not isinstance(text, str) or not text.strip():
            raise ProcessingError(f"Transcript entry {index} has empty transcriptText.")
        entry_time = _parse_timestamp(timestamp_value, f"Transcript entry {index} timestamp")
        entries.append(
            Entry(
                id=f"e{index}",
                speaker=person_name.strip(),
                elapsed=_format_elapsed(entry_time, start_time),
                text=text,
            )
        )

    return Transcript(
        entries=entries,
        meeting_date=meeting_date,
        source_path=source,
        by_id={entry.id: entry for entry in entries},
    )


def compact_view(transcript: Transcript) -> str:
    """Render the compact, numbered view Claude reads instead of raw JSON."""

    lines = [
        f"[{entry.id} · {entry.elapsed}] {entry.speaker}: {entry.text.strip()}"
        for entry in transcript.entries
    ]
    return "\n".join(lines) + "\n"
