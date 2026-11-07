import json
import tempfile
import unittest
from pathlib import Path

from race_attachments import render_race_attachments
from test_weekend_report import snapshot


class RaceAttachmentTests(unittest.TestCase):
    def test_compounds_show_only_selected_circuit_without_guessing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "year": 2026,
                            "title": "컴파운드",
                            "filename": "source.png",
                            "kind": "compound-selection",
                            "circuits": [
                                {
                                    "circuit_key": 65,
                                    "hard": "C3",
                                    "medium": "C4",
                                    "soft": "C5",
                                },
                                {
                                    "circuit_key": 46,
                                    "hard": "C1",
                                    "medium": "C2",
                                    "soft": "C3",
                                },
                            ],
                        }
                    ]
                )
            )
            race = snapshot("Race")
            race["session"].update(year=2026, circuit_key=65)
            page = render_race_attachments(race, root)
            self.assertIn("C5", page)
            self.assertNotIn("C1", page)
            self.assertNotIn("<img", page)
            race["session"]["circuit_key"] = 46
            page = render_race_attachments(race, root)
            self.assertIn("C1", page)
            self.assertNotIn("C5", page)
            race["session"]["circuit_key"] = 999
            self.assertIn("표시하지 않습니다", render_race_attachments(race, root))

    def test_race_year_filter_and_inline_images_without_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text(
                json.dumps(
                    [{"year": 2026, "title": "タイヤ <자료>", "filename": "tyres.png"}]
                )
            )
            race = snapshot("Race")
            race["session"]["year"] = 2026
            self.assertIn("원본 파일 연결 대기", render_race_attachments(race, root))
            (root / "tyres.png").write_bytes(b"fixture-image-bytes")
            text = render_race_attachments(race, root)
            self.assertIn("data:image/png;base64,", text)
            self.assertIn('<img src="data:image/png;base64,', text)
            self.assertNotIn("download=", text)
            self.assertNotIn("<details>", text)
            self.assertIn("&lt;자료&gt;", text)
            race["session"]["year"] = 2025
            self.assertEqual(render_race_attachments(race, root), "")
            self.assertEqual(render_race_attachments(snapshot("Practice 1"), root), "")
