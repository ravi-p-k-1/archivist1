"""Command-line interface for Archivist's JSON transcript pipeline.

Four subcommands mirror the claude-code-action workflow's steps: prepare
writes the extraction inputs, check-evidence lets Claude self-check an
excerpt mid-run via its Bash tool, verify validates the submitted report
after the run, and finalize renders and archives once verify has passed.
"""

import argparse
import os
import sys
from pathlib import Path

from .evidence import verify_action_evidence, verify_report_evidence
from .models import ActionSubmission, ReportSubmission
from .processor import (
    finalize_report,
    resolve_output_paths,
    write_prepare_artifacts,
    write_summary,
)
from .transcript import ProcessingError, load_pending_transcript

PROMPT_PATH = Path(__file__).parent / "prompt.md"


def _archivist_dir(root: Path) -> Path:
    return root / ".archivist"


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to the current directory).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archivist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare", help="Validate the pending transcript and write extraction inputs."
    )
    _add_root_argument(prepare_parser)

    check_parser = subparsers.add_parser(
        "check-evidence", help="Check one evidence excerpt against a transcript entry."
    )
    check_parser.add_argument("entry", help="Compact-view entry id, for example e12.")
    check_parser.add_argument("excerpt", help="Verbatim evidence excerpt to check.")
    _add_root_argument(check_parser)

    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate a submitted report, read from the REPORT environment variable.",
    )
    _add_root_argument(verify_parser)

    finalize_parser = subparsers.add_parser(
        "finalize", help="Render the final report and archive the transcript."
    )
    finalize_parser.add_argument(
        "--model", required=True, help="Filesystem-safe lowercase Claude model name."
    )
    _add_root_argument(finalize_parser)

    return parser


def _cmd_prepare(args: argparse.Namespace) -> int:
    transcript = load_pending_transcript(args.root)
    prompt_md = PROMPT_PATH.read_text(encoding="utf-8")
    write_prepare_artifacts(transcript, prompt_md, _archivist_dir(args.root))
    print(f"Prepared {transcript.source_path} ({len(transcript.entries)} entries).")
    return 0


def _cmd_check_evidence(args: argparse.Namespace) -> int:
    transcript = load_pending_transcript(args.root)
    try:
        action = ActionSubmission(
            action="placeholder", entry=args.entry, evidence_excerpt=args.excerpt
        )
        verify_action_evidence(action, transcript)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("OK")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    archivist_dir = _archivist_dir(args.root)
    raw_report = os.environ.get("REPORT")

    try:
        if not raw_report:
            raise ProcessingError("The REPORT environment variable is not set.")
        transcript = load_pending_transcript(args.root)
        report = ReportSubmission.model_validate_json(raw_report)
        verify_report_evidence(report, transcript)
    except (ProcessingError, ValueError) as exc:
        archivist_dir.mkdir(parents=True, exist_ok=True)
        (archivist_dir / "verify-error.txt").write_text(f"{exc}\n", encoding="utf-8")
        print(f"error: {exc}", file=sys.stderr)
        return 1

    archivist_dir.mkdir(parents=True, exist_ok=True)
    (archivist_dir / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print("Report verified.")
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    archivist_dir = _archivist_dir(args.root)
    report_path = archivist_dir / "report.json"

    try:
        transcript = load_pending_transcript(args.root)
        paths = resolve_output_paths(args.root, transcript.meeting_date, args.model)
        report = None
        if report_path.exists():
            report = ReportSubmission.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        final = finalize_report(report, transcript, paths)
    except (ProcessingError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if final is None:
        write_summary(
            ["Transcript archived.", "", "(Output was already present from an earlier run.)"],
            archivist_dir,
        )
        print(f"Archived transcript at {paths.archive} (output already present).")
        return 0

    write_summary(
        [
            "Transcript processed.",
            "",
            f"- Actions: {len(final.actions)}",
            f"- Decisions: {len(final.decisions)}",
            f"- Open questions: {len(final.open_questions)}",
        ],
        archivist_dir,
    )
    print(f"Output ready at {paths.output_txt}")
    print(f"Archived transcript at {paths.archive}")
    return 0


_HANDLERS = {
    "prepare": _cmd_prepare,
    "check-evidence": _cmd_check_evidence,
    "verify": _cmd_verify,
    "finalize": _cmd_finalize,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.root = args.root.resolve()
    try:
        return _HANDLERS[args.command](args)
    except ProcessingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
