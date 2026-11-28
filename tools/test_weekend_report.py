"""Offline behavioral checks for report generation and collection failures."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import os

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
    def test_unchanged_data_does_not_render_again(self):
        item = snapshot('Practice 1')
        item['data']['session_result'][0]['duration'] = 80.0
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report.save_json(root / 'weekend-2/data/1.json', item)
            (root / 'weekend-2/weekend-report.html').write_text('keep', encoding='utf-8')
            def fetch(endpoint, params):
                return [item['session']] if endpoint == 'sessions' else item['data'][endpoint]
            with patch.object(report, 'fetch', side_effect=fetch), patch.object(report, 'render') as render:
                self.assertEqual(report.collect(2, root), 2)
                render.assert_not_called()
            self.assertEqual((root / 'weekend-2/weekend-report.html').read_text(), 'keep')

    def test_collection_uses_cached_metadata_but_never_publishes_on_data_401(self):
        response = requests.Response()
        response.status_code = 401
        error = requests.HTTPError(response=response)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            item = snapshot('Practice 1')
            report.save_json(root / 'catalog/sessions.json', [item['session']])
            with patch.object(report, 'fetch', side_effect=error), patch.object(report, 'render') as render:
                with self.assertRaises(requests.HTTPError):
                    report.collect(2, root)
                render.assert_not_called()

    def test_fastf1_fallback_can_be_upgraded_to_openf1(self):
        item = snapshot("Practice 1")
        fallback = dict(
            item, data_source="fastf1", status="FastF1 임시 보고서",
            fastf1_source_url="https://livetiming.formula1.com/",
            fastf1_version="test",
        )
        response = requests.Response()
        response.status_code = 401
        error = requests.HTTPError(response=response)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report.save_json(root / "catalog/sessions.json", [item["session"]])
            with patch.object(report, "fetch", side_effect=error), patch(
                "fastf1_source.fallback_snapshot", return_value=fallback
            ) as fetch_fallback:
                self.assertEqual(report.collect(2, root, {1}, allow_fastf1=True), 0)
                fetch_fallback.assert_called_once()
            directory = root / "weekend-2"
            self.assertEqual(report.load_json(directory / "data/1.json")["data_source"], "fastf1")
            self.assertIn("FastF1 임시 보고서", (directory / "weekend-report.html").read_text())
            attempts = report.load_json(root / "catalog/report-attempts.json")
            self.assertFalse(attempts["1"]["completed"])
            self.assertEqual(attempts["1"]["status"], "fastf1_provisional")

            def fetch(endpoint, params):
                return [item["session"]] if endpoint == "sessions" else item["data"][endpoint]

            with patch.object(report, "fetch", side_effect=fetch), patch(
                "fastf1_source.fallback_snapshot"
            ) as fetch_fallback:
                self.assertEqual(report.collect(2, root, allow_fastf1=True), 0)
                fetch_fallback.assert_not_called()
            self.assertNotIn("data_source", report.load_json(directory / "data/1.json"))
            self.assertIn("수집 완료 (OpenF1 기준)", (directory / "weekend-report.html").read_text())

    def test_auth_deferral_preserves_report_and_disables_publication(self):
        response = requests.Response()
        response.status_code = 401
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output'
            page = Path(folder) / 'weekend-report.html'
            page.write_text('previous report', encoding='utf-8')
            with patch('sys.argv', ['weekend_report.py', '--defer-auth']), patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}), patch.object(report, 'collect', side_effect=requests.HTTPError(response=response)):
                self.assertEqual(report.main(), 0)
            self.assertEqual(output.read_text(encoding='utf-8'), 'collected=false\n')
            self.assertEqual(page.read_text(encoding='utf-8'), 'previous report')

    def test_qualifying_laps_use_phase_start_messages_not_lap_times(self):
        item = snapshot()
        item["data"]["race_control"] = [
            {
                "date": "2025-01-01T12:00:00+00:00",
                "qualifying_phase": 1,
                "message": "SESSION STARTED",
            },
            {
                "date": "2025-01-01T12:05:00+00:00",
                "qualifying_phase": 1,
                "message": "SESSION STARTED",
            },
            {
                "date": "2025-01-01T12:20:00+00:00",
                "qualifying_phase": 2,
                "message": "SESSION STARTED",
            },
            {
                "date": "2025-01-01T12:35:00+00:00",
                "qualifying_phase": 2,
                "message": "SESSION FINISHED",
            },
        ]
        windows = report.qualifying_windows(item)
        self.assertEqual(
            report.lap_qualifying_phase(
                {"date_start": "2025-01-01T12:03:00+00:00"}, windows
            ),
            1,
        )
        self.assertEqual(
            report.lap_qualifying_phase(
                {"date_start": "2025-01-01T12:20:00+00:00"}, windows
            ),
            2,
        )
        self.assertIsNone(
            report.lap_qualifying_phase(
                {"date_start": None, "lap_duration": 80}, windows
            )
        )
        self.assertIsNone(
            report.lap_qualifying_phase(
                {"date_start": "2025-01-01T12:40:00+00:00"}, windows
            )
        )

    def test_non_numeric_classification_does_not_break_sorting(self):
        item = snapshot()
        item["data"]["session_result"][0]["position"] = "RT"
        rows = report.summarize(item)
        driver = next(row for row in rows if row["number"] == 1)
        self.assertIsNone(driver["position"])
        self.assertEqual(driver["classification"], "RT")
        self.assertEqual(driver["status"], "API 분류 RT")
        self.assertEqual(report.numeric_position("2"), 2)
        self.assertIsNone(report.numeric_position("RT"))

    def test_tyre_mapping_boundaries_missing_and_conflicts(self):
        stints = [
            {"lap_start": 1, "lap_end": 5, "compound": "SOFT"},
            {"lap_start": 5, "lap_end": 10, "compound": "MEDIUM"},
            {"lap_start": 11, "lap_end": None, "compound": "HARD"},
        ]
        self.assertEqual(report.tyre_for_lap(stints, 1), "SOFT")
        self.assertEqual(report.tyre_for_lap(stints, 5), "UNKNOWN")
        self.assertEqual(report.tyre_for_lap(stints, 6), "MEDIUM")
        self.assertEqual(report.tyre_for_lap(stints, 10), "MEDIUM")
        self.assertEqual(report.tyre_for_lap(stints, 11), "UNKNOWN")

    def test_chart_laps_include_tyre_and_all_drivers_get_verdict(self):
        item = snapshot()
        item["data"]["stints"] = [
            {
                "driver_number": 1,
                "stint_number": 1,
                "lap_start": 1,
                "lap_end": 3,
                "compound": "SOFT",
            }
        ]
        rows = report.summarize(item)
        self.assertEqual(rows[0]["laps"][0]["tyre"], "SOFT")
        text = report.render_verdicts("Qualifying", rows)
        self.assertEqual(text.count("<tr data-search="), 2)
        self.assertIn("DNS", text)
        self.assertIn("1:22.000", text)

    def test_sector_values_and_missing_sectors_are_preserved(self):
        item = snapshot()
        item["data"]["laps"][0].update(
            duration_sector_1=18.926,
            duration_sector_2=35.123,
            duration_sector_3=None,
        )
        lap = report.summarize(item)[0]["laps"][0]
        self.assertEqual(lap["s1"], 18.926)
        self.assertEqual(lap["s2"], 35.123)
        self.assertIsNone(lap["s3"])

    def test_all_drivers_and_deleted_laps(self):
        rows = report.summarize(snapshot())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["fastest"], 82.0)
        self.assertEqual(rows[0]["median"], 82.0)
        self.assertEqual(rows[1]["status"], "DNS")
        self.assertIsNone(rows[1]["fastest"])

    def test_deleted_time_matches_previous_lap_without_deleting_next_lap(self):
        item = snapshot("Practice 1")
        item["data"]["race_control"][0]["message"] = (
            "CAR 1 (TST) TIME 1:20.000 DELETED - TRACK LIMITS LAP 3"
        )
        row = report.summarize(item)[0]
        self.assertEqual(row["fastest"], 82.0)
        self.assertTrue(row["laps"][0]["deleted"])
        self.assertFalse(row["laps"][1]["deleted"])
        item["data"]["race_control"][0]["message"] = (
            "CAR 1 (TST) TIME 1:19.000 DELETED - TRACK LIMITS LAP 3"
        )
        self.assertEqual(report.summarize(item)[0]["fastest"], 80.0)

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
            text = path.read_text(encoding="utf-8")
            self.assertIn("Test &lt;Driver&gt;", text)
            self.assertIn("1:20.300", text)
            self.assertNotIn("@@", text)
            self.assertIn('id="chart-time"', text)
            self.assertNotIn("REPORT_ROWS", text)
            self.assertIn("퀄리파잉 단일 세션 보고서", text)
            self.assertNotIn("프랙티스 1·2·3 + 퀄리파잉", text)

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
                "갱신 실패",
                (root / "weekend-2" / "weekend-report.html").read_text(
                    encoding="utf-8"
                ),
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

    def test_non_ascii_names_round_trip_as_utf8(self):
        item = snapshot()
        item["data"]["drivers"][0]["full_name"] = "Sergio Pérez — 세르히오"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report.save_json(root / "data" / "1.json", item)
            self.assertEqual(report.load_json(root / "data" / "1.json"), item)
            report.render(report.load_offline(root), root / "report.html")
            text = (root / "report.html").read_bytes().decode("utf-8")
            self.assertIn("Sergio Pérez — 세르히오", text)
            self.assertIn("주말 전체 선수 보고서", text)

    def test_null_race_control_message_is_ignored(self):
        item = snapshot()
        item["data"]["race_control"].append({"message": None})
        self.assertEqual(report.summarize(item)[0]["fastest"], 82.0)

    def test_timestamps_are_shown_in_readable_utc(self):
        self.assertEqual(
            report.display_time("2026-11-06T23:14:26.123+00:00"),
            "2026-11-06 23:14 UTC",
        )
        self.assertEqual(report.display_time("미기록"), "미기록")


if __name__ == "__main__":
    unittest.main()
