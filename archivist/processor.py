"""Output and archive lifecycle for the JSON transcript pipeline."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .evidence import verify_report_evidence
from .models import ActionItem, ActionReport, ReportSubmission
from .render import render_report, render_report_json
from .transcript import SOURCE_NAME, ProcessingError, Transcript, compact_view

MODEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class OutputPaths:
    output_txt: Path
    output_json: Path
    archive: Path


def resolve_output_paths(root: Path, meeting_date: str, model: str) -> OutputPaths:
    """Validate the model name and derive this meeting's output/archive paths."""

    if not MODEL_PATTERN.fullmatch(model):
        raise ProcessingError(
            "Model must be a filesystem-safe lowercase name containing only "
            "letters, numbers, dots, underscores, or hyphens."
        )
    root = root.resolve()
    output_dir = root / "output" / meeting_date / model
    return OutputPaths(
        output_txt=output_dir / "action-items.txt",
        output_json=output_dir / "action-items.json",
        archive=root / "archived" / meeting_date / SOURCE_NAME / "transcript.json",
    )


def _write_atomic(destination: Path, contents: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary.write(contents)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, destination)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _remove_empty_transcript_directories(source: Path, transcripts_root: Path) -> None:
    """Remove empty source/date directories without removing transcripts/."""

    for directory in (source.parent, source.parent.parent):
        try:
            directory.relative_to(transcripts_root)
        except ValueError:
            break
        try:
            directory.rmdir()
        except OSError:
            # A nonempty directory, or one that cannot be removed, is preserved.
            break


def _archive_source(transcript: Transcript, archive: Path) -> None:
    if archive.exists():
        raise ProcessingError(f"Archive destination already exists: {archive}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        transcript.source_path.replace(archive)
    except OSError as exc:
        raise ProcessingError(
            "The report was written, but moving the transcript to archived/ failed. "
            "Run finalize again to retry archiving."
        ) from exc
    transcripts_root = transcript.source_path.parents[2]
    _remove_empty_transcript_directories(transcript.source_path, transcripts_root)


def write_prepare_artifacts(transcript: Transcript, prompt_md: str, archivist_dir: Path) -> None:
    """Write the compact view, schema, and prompt that prime extraction."""

    prompt_text = (
        f"{prompt_md.strip()}\n\n"
        "The meeting's compact transcript view is at .archivist/view.txt. "
        "Read it, then submit your report."
    )
    _write_atomic(archivist_dir / "view.txt", compact_view(transcript))
    _write_atomic(
        archivist_dir / "schema.json",
        json.dumps(ReportSubmission.model_json_schema(), indent=2),
    )
    _write_atomic(archivist_dir / "prompt.txt", prompt_text)


def finalize_report(
    report: ReportSubmission | None,
    transcript: Transcript,
    paths: OutputPaths,
) -> ActionReport | None:
    """Render outputs (if needed) and archive the source transcript.

    If the output files already exist from an earlier run that wrote them
    but failed only at archiving, this retries just the archive step and
    returns None - no report is needed for that recovery path.
    """

    output_complete = paths.output_txt.exists() and paths.output_json.exists()
    output_partial = paths.output_txt.exists() != paths.output_json.exists()
    if output_partial:
        raise ProcessingError(
            f"Existing output at {paths.output_txt.parent} is incomplete; refusing to proceed."
        )
    if output_complete:
        _archive_source(transcript, paths.archive)
        return None

    if paths.archive.exists():
        raise ProcessingError(f"Archive destination already exists: {paths.archive}")
    if report is None:
        raise ProcessingError(
            "A validated report (.archivist/report.json) is required to create a new output. "
            "Run verify first."
        )

    verify_report_evidence(report, transcript)

    final = ActionReport(
        actions=[
            ActionItem(
                action=action.action,
                owner=action.owner,
                due_date=action.due_date,
                evidence_excerpt=action.evidence_excerpt,
                speaker=transcript.by_id[action.entry].speaker,
                timestamp=transcript.by_id[action.entry].elapsed,
            )
            for action in report.actions
        ],
        decisions=report.decisions,
        open_questions=report.open_questions,
    )

    try:
        _write_atomic(paths.output_txt, render_report(final))
        _write_atomic(paths.output_json, render_report_json(final))
    except OSError as exc:
        raise ProcessingError("The output report could not be written.") from exc

    _archive_source(transcript, paths.archive)
    return final


def write_summary(summary_lines: list[str], archivist_dir: Path) -> None:
    """Write a short Markdown summary for the PR comment."""

    _write_atomic(archivist_dir / "summary.md", "\n".join(summary_lines) + "\n")
