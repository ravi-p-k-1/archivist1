import tempfile
import unittest
from pathlib import Path

from archivist.transcript import ProcessingError, compact_view, load_pending_transcript
from tests.helpers import FIXTURE_DATE, load_fixture, write_transcript


class LoadPendingTranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_loads_and_numbers_entries(self) -> None:
        write_transcript(self.root, FIXTURE_DATE, load_fixture())

        transcript = load_pending_transcript(self.root)

        self.assertEqual(transcript.meeting_date, FIXTURE_DATE)
        self.assertEqual([entry.id for entry in transcript.entries], ["e1", "e2", "e3"])
        self.assertEqual(transcript.by_id["e1"].speaker, "Alex")
        self.assertEqual(transcript.by_id["e1"].elapsed, "00:00:05")
        self.assertEqual(transcript.by_id["e2"].elapsed, "00:00:12")
        self.assertEqual(transcript.by_id["e3"].elapsed, "00:05:30")

    def test_compact_view_format(self) -> None:
        write_transcript(self.root, FIXTURE_DATE, load_fixture())
        transcript = load_pending_transcript(self.root)

        view = compact_view(transcript)

        self.assertIn("[e1 · 00:00:05] Alex: Let's get started.", view)
        self.assertIn("[e2 · 00:00:12] Priya:", view)

    def test_rejects_non_advanced_body_type(self) -> None:
        payload = load_fixture()
        payload["webhookBodyType"] = "basic"
        write_transcript(self.root, FIXTURE_DATE, payload)

        with self.assertRaisesRegex(ProcessingError, "advanced"):
            load_pending_transcript(self.root)

    def test_rejects_entry_missing_a_field(self) -> None:
        payload = load_fixture()
        del payload["transcript"][0]["personName"]
        write_transcript(self.root, FIXTURE_DATE, payload)

        with self.assertRaisesRegex(ProcessingError, "missing"):
            load_pending_transcript(self.root)

    def test_rejects_non_iso_timestamp(self) -> None:
        payload = load_fixture()
        payload["transcript"][0]["timestamp"] = "not-a-timestamp"
        write_transcript(self.root, FIXTURE_DATE, payload)

        with self.assertRaisesRegex(ProcessingError, "ISO 8601"):
            load_pending_transcript(self.root)

    def test_rejects_end_before_start(self) -> None:
        payload = load_fixture()
        payload["meetingEndTimestamp"] = "2025-06-15T16:00:00.000Z"
        write_transcript(self.root, FIXTURE_DATE, payload)

        with self.assertRaisesRegex(ProcessingError, "meetingEndTimestamp"):
            load_pending_transcript(self.root)

    def test_rejects_folder_date_mismatch(self) -> None:
        payload = load_fixture()
        write_transcript(self.root, "2025-06-16", payload)

        with self.assertRaisesRegex(ProcessingError, "does not match"):
            load_pending_transcript(self.root)

    def test_rejects_more_than_one_pending_transcript(self) -> None:
        write_transcript(self.root, FIXTURE_DATE, load_fixture())
        other = load_fixture()
        other["meetingStartTimestamp"] = "2025-06-16T17:00:00.000Z"
        other["meetingEndTimestamp"] = "2025-06-16T17:28:00.000Z"
        for entry in other["transcript"]:
            entry["timestamp"] = entry["timestamp"].replace("2025-06-15", "2025-06-16")
        write_transcript(self.root, "2025-06-16", other)

        with self.assertRaisesRegex(ProcessingError, "one pending transcript"):
            load_pending_transcript(self.root)

    def test_rejects_when_already_archived(self) -> None:
        write_transcript(self.root, FIXTURE_DATE, load_fixture())
        archive = self.root / "archived" / FIXTURE_DATE / "meet" / "transcript.json"
        archive.parent.mkdir(parents=True)
        archive.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ProcessingError, "Archive destination already exists"):
            load_pending_transcript(self.root)


if __name__ == "__main__":
    unittest.main()
