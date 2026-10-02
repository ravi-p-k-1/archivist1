import json
import tempfile
import unittest
from pathlib import Path

from archivist.evidence import EvidenceVerificationError
from archivist.models import ActionSubmission, ReportSubmission
from archivist.processor import (
    finalize_report,
    resolve_output_paths,
    write_prepare_artifacts,
    write_summary,
)
from archivist.transcript import ProcessingError, load_pending_transcript
from tests.helpers import FIXTURE_DATE, load_fixture, write_transcript


def supported_report() -> ReportSubmission:
    return ReportSubmission(
        actions=[
            ActionSubmission(
                action="Send the doc",
                owner="Priya",
                entry="e2",
                evidence_excerpt="I'll send the doc by Friday.",
            )
        ],
        decisions=["Ship the new flow next week."],
        open_questions=["Which model should run?"],
    )


class ProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_transcript(self.root, FIXTURE_DATE, load_fixture())
        self.transcript = load_pending_transcript(self.root)
        self.paths = resolve_output_paths(self.root, FIXTURE_DATE, "claude-test")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_success_writes_output_and_archives_source(self) -> None:
        final = finalize_report(supported_report(), self.transcript, self.paths)

        self.assertIsNotNone(final)
        self.assertEqual(final.actions[0].speaker, "Priya")
        self.assertEqual(final.actions[0].timestamp, "00:00:12")
        self.assertFalse(self.transcript.source_path.exists())
        self.assertTrue(self.paths.archive.exists())
        self.assertTrue(self.paths.output_txt.exists())
        self.assertTrue(self.paths.output_json.exists())
        self.assertFalse(self.transcript.source_path.parent.exists())
        self.assertFalse(self.transcript.source_path.parent.parent.exists())
        self.assertTrue((self.root / "transcripts").exists())

        text = self.paths.output_txt.read_text(encoding="utf-8")
        self.assertIn("1. Action: Send the doc", text)
        self.assertIn("Speaker: Priya", text)
        json_report = json.loads(self.paths.output_json.read_text(encoding="utf-8"))
        self.assertEqual(json_report["actions"][0]["speaker"], "Priya")

    def test_missing_evidence_leaves_everything_in_place(self) -> None:
        report = supported_report().model_copy(deep=True)
        report.actions[0].evidence_excerpt = "This does not exist."

        with self.assertRaises(EvidenceVerificationError):
            finalize_report(report, self.transcript, self.paths)

        self.assertTrue(self.transcript.source_path.exists())
        self.assertFalse(self.paths.output_txt.exists())
        self.assertFalse(self.paths.archive.exists())

    def test_recovery_retries_only_archive_when_output_already_complete(self) -> None:
        self.paths.output_txt.parent.mkdir(parents=True)
        self.paths.output_txt.write_text("existing text report", encoding="utf-8")
        self.paths.output_json.write_text("{}", encoding="utf-8")

        final = finalize_report(None, self.transcript, self.paths)

        self.assertIsNone(final)
        self.assertFalse(self.transcript.source_path.exists())
        self.assertTrue(self.paths.archive.exists())
        self.assertEqual(self.paths.output_txt.read_text(encoding="utf-8"), "existing text report")

    def test_partial_output_is_rejected(self) -> None:
        self.paths.output_txt.parent.mkdir(parents=True)
        self.paths.output_txt.write_text("existing text report", encoding="utf-8")

        with self.assertRaisesRegex(ProcessingError, "incomplete"):
            finalize_report(supported_report(), self.transcript, self.paths)

    def test_new_report_requires_a_validated_submission(self) -> None:
        with self.assertRaisesRegex(ProcessingError, "validated report"):
            finalize_report(None, self.transcript, self.paths)

        self.assertTrue(self.transcript.source_path.exists())
        self.assertFalse(self.paths.output_txt.exists())

    def test_archive_preserves_nonempty_source_directories(self) -> None:
        metadata = self.transcript.source_path.parent / "notes.txt"
        metadata.write_text("Keep this file.", encoding="utf-8")

        finalize_report(supported_report(), self.transcript, self.paths)

        self.assertTrue(metadata.exists())
        self.assertTrue(self.transcript.source_path.parent.exists())
        self.assertTrue(self.transcript.source_path.parent.parent.exists())

    def test_prepare_writes_view_schema_and_prompt(self) -> None:
        archivist_dir = self.root / ".archivist"
        write_prepare_artifacts(self.transcript, "Extraction rules.", archivist_dir)

        view = (archivist_dir / "view.txt").read_text(encoding="utf-8")
        schema = json.loads((archivist_dir / "schema.json").read_text(encoding="utf-8"))
        prompt = (archivist_dir / "prompt.txt").read_text(encoding="utf-8")

        self.assertIn("[e1 · 00:00:05] Alex:", view)
        self.assertIn("actions", schema["properties"])
        self.assertIn("Extraction rules.", prompt)
        self.assertIn(".archivist/view.txt", prompt)

    def test_write_summary(self) -> None:
        archivist_dir = self.root / ".archivist"
        write_summary(["Transcript processed.", "", "- Actions: 1"], archivist_dir)

        self.assertIn("Actions: 1", (archivist_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
