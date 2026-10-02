"""Deterministic grounding checks for generated action items.

`verify_evidence_excerpts` is the original whole-transcript check used by
the Claude-Agent-SDK extractor in claude.py (unused by the JSON pipeline,
kept until phase 5 removes claude.py). `verify_action_evidence` /
`verify_report_evidence` are the per-entry checks the JSON pipeline uses
instead, since Claude now cites a compact-view entry id rather than being
checked against the whole transcript.
"""

import re

from .models import ActionReport, ActionSubmission, ReportSubmission
from .transcript import Transcript


class EvidenceVerificationError(ValueError):
    """Raised when generated evidence cannot be grounded in its source."""


def normalize_whitespace(value: str) -> str:
    """Collapse all whitespace so wrapped transcript excerpts still match."""

    return re.sub(r"\s+", " ", value).strip()


def verify_evidence_excerpts(report: ActionReport, transcript: str) -> None:
    """Require every action's normalized evidence to occur in the transcript."""

    normalized_transcript = normalize_whitespace(transcript)
    for index, item in enumerate(report.actions, start=1):
        normalized_excerpt = normalize_whitespace(item.evidence_excerpt)
        if normalized_excerpt not in normalized_transcript:
            raise EvidenceVerificationError(
                f"Action {index} has an evidence excerpt that is absent from the transcript."
            )


def verify_action_evidence(action: ActionSubmission, transcript: Transcript) -> None:
    """Require one action's evidence to occur in the entry it cites."""

    entry = transcript.by_id.get(action.entry)
    if entry is None:
        raise EvidenceVerificationError(f"Action cites unknown entry id: {action.entry}.")

    normalized_excerpt = normalize_whitespace(action.evidence_excerpt)
    normalized_entry = normalize_whitespace(entry.text)
    if normalized_excerpt not in normalized_entry:
        raise EvidenceVerificationError(
            f"Action's evidence excerpt is absent from entry {action.entry}."
        )


def verify_report_evidence(report: ReportSubmission, transcript: Transcript) -> None:
    """Require every action's evidence in the report to be grounded."""

    for index, action in enumerate(report.actions, start=1):
        try:
            verify_action_evidence(action, transcript)
        except EvidenceVerificationError as exc:
            raise EvidenceVerificationError(f"Action {index}: {exc}") from exc
