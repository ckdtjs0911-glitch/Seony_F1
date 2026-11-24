"""Check telemetry alignment, missing signals and report embedding without network."""
import json
import tempfile
import unittest
from pathlib import Path

from report_video import epoch, past_sample, render_section, select_scene


class VideoTests(unittest.TestCase):
    def test_never_uses_future_or_stale_signal(self):
        rows = [{"date": "2026-11-22T04:00:00+00:00", "brake": 0},
                {"date": "2026-11-22T04:00:00.500+00:00", "brake": 100}]
        start = epoch(rows[0]["date"])
        self.assertIsNone(past_sample(rows, start - .01))
        self.assertEqual(past_sample(rows, start + .49)["brake"], 0)
        self.assertEqual(past_sample(rows, start + .5)["brake"], 100)
        self.assertIsNone(past_sample(rows, start + 1.51))

    def test_video_self_contained_and_session_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"session_key": 12, "fetched_at": "time", "videos": [{"file": "test.mp4", "title": "<test>", "description": "actual"}]}
            (root / "12-videos.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "test.mp4").write_bytes(b"mp4")
            snapshot = {"session": {"session_key": 12, "session_name": "Race"}}
            page = render_section(snapshot, root)
            self.assertIn("data:video/mp4;base64,bXA0", page)
            self.assertIn("&lt;test&gt;", page)
            self.assertIn('autoplay muted loop playsinline', page)
            snapshot['session']['session_name'] = 'Qualifying'
            self.assertEqual(render_section(snapshot, root), '')
            snapshot['session']['session_name'] = 'Race'
            manifest["session_key"] = 99
            (root / "12-videos.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(render_section(snapshot, root), "")

    def test_selects_overlapping_time_not_separate_lap_start(self):
        snapshot = {"data": {"session_result": [{"position": 2, "driver_number": 2}, {"position": 1, "driver_number": 1}], "laps": []}}
        for driver, start in [(1, "2026-11-22T04:00:00+00:00"), (2, "2026-11-22T04:00:01+00:00")]:
            snapshot["data"]["laps"].append({"driver_number": driver, "lap_number": 1, "date_start": start, "lap_duration": 90})
        drivers, lap, start, end = select_scene(snapshot)
        self.assertEqual(drivers, [1, 2])
        self.assertEqual(end - start, 89)


if __name__ == "__main__":
    unittest.main()
