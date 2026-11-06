"""Offline behavioral checks for report generation and collection failures."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

import weekend_report as report


def snapshot(name="Qualifying"):
    return {
        "session": {
            "session_name": name,
            "session_key": 1,
            "meeting_key": 2,
            "date_start": "2025-01-01T12:00:00+00:00",
            "date_end": "2025-01-01T13:00:00+00:00",
        },
        "status": "test",
        "data": {
            "drivers": [
                {"driver_number": 1, "full_name": "Test <Driver>", "team_name": "Team"},
                {"driver_number": 2, "full_name": "No laps", "team_name": "Team"},
            ],
            "session_result": [
                {"driver_number": 1, "position": 1, "duration": [82.1, 81.2, 80.3]},
                {"driver_number": 2, "position": None, "dns": True},
            ],
            "laps": [
                {
                    "driver_number": 1,
                    "lap_number": 2,
                    "lap_duration": 80.0,
                    "date_start": "2025-01-01T12:10:00+00:00",
                },
                {
                    "driver_number": 1,
                    "lap_number": 3,
                    "lap_duration": 82.0,
                    "date_start": "2025-01-01T12:12:00+00:00",
                },
            ],
            "race_control": [
                {"message": "CAR 1 (TST) TIME 1:20.000 DELETED - TRACK LIMITS LAP 2"}
            ],
            "stints": [],
            "pit": [],
        },
    }


class ReportTests(unittest.TestCase):
    def test_all_drivers_and_deleted_laps(self):
        rows = report.summarize(snapshot())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["fastest"], 82.0)
        self.assertEqual(rows[0]["median"], 82.0)
        self.assertEqual(rows[1]["status"], "DNS")
        self.assertIsNone(rows[1]["fastest"])

    def test_qualifying_uses_official_phase_array(self):
        row = report.summarize(snapshot())[0]
        self.assertEqual(row["q"], [82.1, 81.2, 80.3])
        item = snapshot()
        item["data"]["session_result"][0]["duration"] = 80.3
        self.assertEqual(report.summarize(item)[0]["q"], [None, None, None])

    def test_stint_sample_excludes_pit_entry(self):
        item = snapshot()
        item["data"]["stints"] = [
            {
                "driver_number": 1,
                "stint_number": 1,
                "lap_start": 1,
                "lap_end": 3,
                "compound": "MEDIUM",
            }
        ]
        item["data"]["pit"] = [
            {"driver_number": 1, "lap_number": 3, "date": "2025-01-01T12:12:05+00:00"}
        ]
        row = report.summarize(item)[0]
        self.assertEqual(row["pits"], 1)
        self.assertEqual(row["stints"][0]["sample_count"], 0)
        self.assertIsNone(row["median"])

    def test_html_escapes_names_and_embeds_chart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.html"
            report.render([snapshot()], path)
            text = path.read_text()
            self.assertIn("Test &lt;Driver&gt;", text)
            self.assertIn("1:20.300", text)
            self.assertNotIn("@@", text)
            self.assertIn('id="chart"', text)

    def test_failed_refresh_preserves_last_success(self):
        item = snapshot()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "weekend-2" / "data" / "1.json"
            report.save_json(path, item)
            before = path.read_bytes()
            with patch.object(
                report,
                "fetch",
                side_effect=[[item["session"]], requests.ConnectionError("offline")],
            ):
                code = report.collect(2, root)
            self.assertEqual(code, 1)
            self.assertEqual(path.read_bytes(), before)
            self.assertIn(
                "갱신 실패", (root / "weekend-2" / "weekend-report.html").read_text()
            )

    def test_empty_results_are_retried_not_saved(self):
        item = snapshot()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def fetch(endpoint, params):
                return (
                    [item["session"]]
                    if endpoint == "sessions"
                    else item["data"].get(endpoint, [])
                    if endpoint != "session_result"
                    else []
                )

            with patch.object(report, "fetch", side_effect=fetch):
                self.assertEqual(report.collect(2, root), 1)
            self.assertFalse((root / "weekend-2" / "data" / "1.json").exists())


if __name__ == "__main__":
    unittest.main()
