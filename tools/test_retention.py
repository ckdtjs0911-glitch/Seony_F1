import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from retention import first_year, prune


class RetentionTests(unittest.TestCase):
    def test_reference_images_expire_with_their_year(self):
        with tempfile.TemporaryDirectory() as folder:
            reports = Path(folder)
            assets = reports / "attachments"
            assets.mkdir()
            entries = [
                {"year": year, "filename": f"{year}.png"} for year in (2026, 2027)
            ]
            (assets / "manifest.json").write_text(json.dumps(entries))
            for entry in entries:
                (assets / entry["filename"]).write_bytes(b"fixture")
            prune(reports, now=datetime(2029, 1, 1, tzinfo=timezone.utc))
            self.assertFalse((assets / "2026.png").exists())
            self.assertTrue((assets / "2027.png").exists())
            self.assertEqual(
                json.loads((assets / "manifest.json").read_text()), entries[1:]
            )

    def test_korean_new_year_window(self):
        self.assertEqual(
            first_year(datetime(2026, 12, 31, 14, 59, tzinfo=timezone.utc)), 2024
        )
        self.assertEqual(
            first_year(datetime(2026, 12, 31, 15, 0, tzinfo=timezone.utc)), 2025
        )

    def test_2027_deletes_2024_and_preserves_newer_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reports = root / "reports"
            raw = root / "raw"
            raw.mkdir()
            sessions = [
                {
                    "year": y,
                    "session_key": y,
                    "meeting_key": y,
                    "date_start": f"{y}-01-01T00:00:00+00:00",
                }
                for y in [2024, 2025, 2026, 2027]
            ]
            catalog = reports / "catalog"
            catalog.mkdir(parents=True)
            (catalog / "sessions.json").write_text(json.dumps(sessions))
            for session in sessions:
                path = reports / f'weekend-{session["year"]}' / "data"
                path.mkdir(parents=True)
                (path / "snapshot.json").write_text(json.dumps({"session": session}))
                (raw / str(session["session_key"])).mkdir()
            with sqlite3.connect(raw / "manifest.sqlite") as db:
                db.execute("create table downloads(job text)")
                db.executemany(
                    "insert into downloads values (?)",
                    [(str(y) + "/laps",) for y in [2024, 2025]],
                )
            prune(reports, raw, datetime(2027, 1, 1, tzinfo=timezone.utc))
            self.assertFalse((reports / "weekend-2024").exists())
            self.assertFalse((raw / "2024").exists())
            for year in [2025, 2026, 2027]:
                self.assertTrue((reports / f"weekend-{year}").exists())
            self.assertEqual(
                [
                    s["year"]
                    for s in json.loads((catalog / "sessions.json").read_text())
                ],
                [2025, 2026, 2027],
            )
            with sqlite3.connect(raw / "manifest.sqlite") as db:
                self.assertEqual(
                    db.execute("select job from downloads").fetchall(), [("2025/laps",)]
                )
