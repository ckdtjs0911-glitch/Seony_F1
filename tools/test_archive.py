import base64
import gzip
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import build_archive
import weekend_report as report
from test_weekend_report import snapshot


class ArchiveTests(unittest.TestCase):
    def test_repeated_reference_image_is_stored_once(self):
        year = datetime.now(timezone.utc).year
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / "attachments"
            assets.mkdir()
            (assets / "shared.png").write_bytes(b"shared-test-image")
            report.save_json(
                assets / "manifest.json",
                [{"year": year, "title": "참고 이미지", "filename": "shared.png"}],
            )
            for key in (1, 2):
                item = snapshot("Race")
                item["session"].update(year=year, session_key=key)
                report.save_json(root / "weekend-2" / "data" / f"{key}.json", item)
            with patch("race_attachments.ATTACHMENTS", assets):
                build_archive.build(root)
            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertEqual(page.count("data:image/png;base64,"), 1)
            entries = json.loads(
                page.split("const entries=", 1)[1].split(";const year=", 1)[0]
            )
            self.assertEqual(
                entries[0]["attachment_assets"], entries[1]["attachment_assets"]
            )

    def test_annual_report_contains_only_current_year_with_identical_data(self):
        current_year = datetime.now(timezone.utc).year
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for year in (current_year - 1, current_year):
                item = snapshot("Practice 1")
                item["session"].update(year=year, session_key=year, meeting_key=year)
                report.save_json(
                    root / f"weekend-{year}" / "data" / f"{year}.json", item
                )
            build_archive.build(root)

            def entries(name):
                text = (root / name).read_text(encoding="utf-8")
                return json.loads(
                    text.split("const entries=", 1)[1].split(";const year=", 1)[0]
                )

            full = entries("index.html")
            annual = entries("current-year.html")
            self.assertEqual(len(full), 2)
            self.assertEqual(
                annual, [entry for entry in full if entry["year"] == current_year]
            )
            self.assertTrue(annual[0]["payload"])

    def test_accumulation_and_catalog_missing_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            item = snapshot("Practice 1")
            item["session"].update(
                year=2025, country_name="Australia", location="Melbourne"
            )
            missing = dict(item["session"], session_key=3, session_name="Practice 2")
            report.save_json(
                root / "catalog" / "sessions.json", [item["session"], missing]
            )
            report.save_json(root / "weekend-2" / "data" / "1.json", item)
            original = (root / "weekend-2" / "data" / "1.json").read_bytes()
            build_archive.build(root)
            text = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("호주 그랑프리", text)
            self.assertNotIn("ARCHIVE_DATA", text)
            entries = json.loads(
                text.split("const entries=", 1)[1].split(";const year=", 1)[0]
            )
            downloaded = next(e for e in entries if e["key"] == 1)
            html = gzip.decompress(base64.b64decode(downloaded["payload"])).decode()
            self.assertIn("2025 호주 그랑프리", html)
            self.assertIsNone(next(e for e in entries if e["key"] == 3)["payload"])
            build_archive.build(root)
            self.assertEqual(
                (root / "weekend-2" / "data" / "1.json").read_bytes(), original
            )
