import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from archivist.cli import main
from tests.helpers import FIXTURE_DATE, load_fixture, write_transcript


def supported_report_json() -> str:
    return json.dumps(
        {
            "actions": [
                {
                    "action": "Send the doc",
                    "owner": "Priya",
                    "due_date": "Friday",
                    "entry": "e2",
                    "evidence_excerpt": "I'll send the doc by Friday.",
                }
            ],
            "decisions": ["Ship the new flow next week."],
            "open_questions": [],
        }
    )


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = write_transcript(self.root, FIXTURE_DATE, load_fixture())
        self.archivist_dir = self.root / ".archivist"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_prepare_writes_artifacts(self) -> None:
        exit_code = main(["prepare", "--root", str(self.root)])

        self.assertEqual(exit_code, 0)
        self.assertTrue((self.archivist_dir / "view.txt").exists())
        self.assertTrue((self.archivist_dir / "schema.json").exists())
        self.assertTrue((self.archivist_dir / "prompt.txt").exists())

    def test_prepare_reports_contract_violations(self) -> None:
        self.source.write_text('{"webhookBodyType": "basic"}', encoding="utf-8")

        with patch("sys.stderr") as stderr:
            exit_code = main(["prepare", "--root", str(self.root)])

        self.assertEqual(exit_code, 1)
        printed = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("advanced", printed)

    def test_check_evidence_ok(self) -> None:
        exit_code = main(
            ["check-evidence", "e2", "I'll send the doc by Friday.", "--root", str(self.root)]
        )
        self.assertEqual(exit_code, 0)

    def test_check_evidence_rejects_unknown_entry(self) -> None:
        with patch("sys.stderr") as stderr:
            exit_code = main(["check-evidence", "e99", "anything", "--root", str(self.root)])

        self.assertEqual(exit_code, 1)
        printed = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("unknown entry id", printed)

    def test_verify_requires_report_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.stderr"):
                exit_code = main(["verify", "--root", str(self.root)])

        self.assertEqual(exit_code, 1)
        self.assertTrue((self.archivist_dir / "verify-error.txt").exists())

    def test_verify_success_writes_report_json(self) -> None:
        with patch.dict(os.environ, {"REPORT": supported_report_json()}):
            exit_code = main(["verify", "--root", str(self.root)])

        self.assertEqual(exit_code, 0)
        saved = json.loads((self.archivist_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["actions"][0]["entry"], "e2")

    def test_verify_rejects_ungrounded_excerpt(self) -> None:
        bad_report = json.dumps(
            {
                "actions": [
                    {"action": "Do a thing", "entry": "e1", "evidence_excerpt": "not present"}
                ],
                "decisions": [],
                "open_questions": [],
            }
        )
        with patch.dict(os.environ, {"REPORT": bad_report}):
            with patch("sys.stderr"):
                exit_code = main(["verify", "--root", str(self.root)])

        self.assertEqual(exit_code, 1)
        self.assertIn("absent from entry", (self.archivist_dir / "verify-error.txt").read_text())

    def test_finalize_requires_verify_first(self) -> None:
        with patch("sys.stderr") as stderr:
            exit_code = main(["finalize", "--model", "claude-test", "--root", str(self.root)])

        self.assertEqual(exit_code, 1)
        printed = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("validated report", printed)

    def test_finalize_succeeds_after_verify(self) -> None:
        with patch.dict(os.environ, {"REPORT": supported_report_json()}):
            self.assertEqual(main(["verify", "--root", str(self.root)]), 0)

        exit_code = main(["finalize", "--model", "claude-test", "--root", str(self.root)])

        self.assertEqual(exit_code, 0)
        output = self.root / "output" / FIXTURE_DATE / "claude-test" / "action-items.txt"
        self.assertTrue(output.exists())
        self.assertIn("Actions: 1", (self.archivist_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
