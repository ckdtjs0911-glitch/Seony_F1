import unittest

from race_pitstops import render_pitstops
from test_weekend_report import snapshot
import weekend_report as report


class PitStopTests(unittest.TestCase):
    def test_stationary_lane_and_legacy_times_are_distinct(self):
        item = snapshot("Race")
        item["data"]["pit"] = [
            {
                "driver_number": 1,
                "lap_number": 2,
                "date": "2025-01-01T12:11:00+00:00",
                "stop_duration": 2.123,
                "lane_duration": 22.5,
            },
            {
                "driver_number": 1,
                "lap_number": 3,
                "date": "2025-01-01T12:12:00+00:00",
                "stop_duration": None,
                "pit_duration": 25.2,
            },
            {
                "driver_number": 1,
                "lap_number": 1,
                "date": "2025-01-01T11:00:00+00:00",
                "lane_duration": 999,
            },
        ]
        page = render_pitstops(item, report.summarize(item))
        self.assertIn("2.123초", page)
        self.assertIn("22.500초", page)
        self.assertIn("25.200초 (기존 pit_duration)", page)
        self.assertIn("2025-01-01 21:11:00", page)
        self.assertNotIn("999.000초", page)
        self.assertIn("미제공", page)
        self.assertIn("기록 없음", page)
        self.assertIn("Test &lt;Driver&gt;", page)
        self.assertEqual(page.count("data-pit-driver="), 2)
        self.assertEqual(render_pitstops(snapshot(), []), "")

    def test_images_are_last_and_pits_are_immediately_before(self):
        import tempfile
        from pathlib import Path

        item = snapshot("Race")
        item["session"]["year"] = 2026
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.html"
            report.render([item], path)
            page = path.read_text(encoding="utf-8")
            self.assertLess(
                page.index('<section id="race-pit-stops"'),
                page.index('<section id="race-tyre-attachments"'),
            )
            self.assertLess(
                page.index('id="lap-sector-analysis"'),
                page.index('<section id="race-pit-stops"'),
            )
            self.assertLess(
                page.index('<section id="race-tyre-attachments"'), page.index("</main>")
            )
