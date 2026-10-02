import tempfile
import unittest
from pathlib import Path

from archivist.evidence import (
    EvidenceVerificationError,
    verify_action_evidence,
    verify_report_evidence,
)
from archivist.models import ActionSubmission, ReportSubmission
from archivist.transcript import load_pending_transcript
from tests.helpers import FIXTURE_DATE, load_fixture, write_transcript


class PerEntryEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_transcript(self.root, FIXTURE_DATE, load_fixture())
        self.transcript = load_pending_transcript(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_excerpt_grounded_in_its_cited_entry(self) -> None:
        action = ActionSubmission(
            action="Send the doc", entry="e2", evidence_excerpt="I'll send the doc by Friday."
        )
        verify_action_evidence(action, self.transcript)

    def test_rejects_excerpt_from_a_different_entry(self) -> None:
        action = ActionSubmission(
            action="Send the doc", entry="e1", evidence_excerpt="I'll send the doc by Friday."
        )
        with self.assertRaisesRegex(EvidenceVerificationError, "absent from entry e1"):
            verify_action_evidence(action, self.transcript)

    def test_rejects_unknown_entry_id(self) -> None:
        action = ActionSubmission(action="Do a thing", entry="e99", evidence_excerpt="anything")
        with self.assertRaisesRegex(EvidenceVerificationError, "unknown entry id"):
            verify_action_evidence(action, self.transcript)

    def test_report_check_reports_the_failing_action_index(self) -> None:
        report = ReportSubmission(
            actions=[
                ActionSubmission(
                    action="Send the doc",
                    entry="e2",
                    evidence_excerpt="I'll send the doc by Friday.",
                ),
                ActionSubmission(action="Bad one", entry="e1", evidence_excerpt="not present"),
            ]
        )
        with self.assertRaisesRegex(EvidenceVerificationError, "^Action 2:"):
            verify_report_evidence(report, self.transcript)


if __name__ == "__main__":
    unittest.main()
