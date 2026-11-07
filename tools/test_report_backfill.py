import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backfill_reports
import weekend_report as report
from test_weekend_report import snapshot


class BatchReportTests(unittest.TestCase):
    def test_meeting_response_is_split_into_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reports = root / "reports"
            item = snapshot("Practice 1")
            first = dict(item["session"], year=2025)
            second = dict(first, session_key=2, session_name="Practice 2")
            report.save_json(reports / "catalog" / "sessions.json", [first, second])

            def fetch(endpoint, params):
                self.assertEqual(params, {"meeting_key": 2})
                return [
                    dict(record, session_key=key)
                    for key in [1, 2]
                    for record in item["data"].get(endpoint, [])
                ]

            with patch.object(report, "fetch", side_effect=fetch) as api, patch.object(
                backfill_reports, "build"
            ):
                backfill_reports.run(reports, root / "raw")
            self.assertEqual(api.call_count, 6)
            for key in [1, 2]:
                value = report.load_json(reports / "weekend-2" / "data" / f"{key}.json")
                self.assertTrue(
                    all(r["session_key"] == key for r in value["data"]["drivers"])
                )
                self.assertTrue((root / "raw" / str(key) / "laps.json.gz").exists())
