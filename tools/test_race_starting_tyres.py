import base64
import gzip
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import build_archive
import weekend_report as report
from race_attachments import render_race_attachments
from race_starting_tyres import render_starting_tyres, summarize_start
from test_weekend_report import snapshot


def race(compound="INTERMEDIATE"):
    item = snapshot("Race")
    item["session"]["year"] = datetime.now(timezone.utc).year
    item["data"]["session_result"][0].update(number_of_laps=1, dns=False)
    item["data"]["session_result"][1].update(number_of_laps=0, dns=True)
    item["data"]["stints"] = [
        {
            "driver_number": 1,
            "stint_number": 1,
            "lap_start": 1,
            "lap_end": 10,
            "compound": compound,
        },
        {
            "driver_number": 2,
            "stint_number": 1,
            "lap_start": 1,
            "lap_end": 1,
            "compound": "SOFT",
        },
    ]
    return item


class StartingTyreTests(unittest.TestCase):
    def test_dns_with_lap_and_stint_records_is_excluded(self):
        item = race()
        item["data"]["laps"].append(
            {"driver_number": 2, "lap_number": 1, "lap_duration": 90}
        )
        result = summarize_start(item)
        self.assertEqual(result["starters"], 1)
        self.assertEqual(result["dns"], 1)
        self.assertEqual(result["counts"], {"INTERMEDIATE": 1})

    def test_later_stint_never_fills_missing_start_tyre(self):
        item = race()
        item["data"]["stints"][0]["lap_start"] = 2
        self.assertEqual(summarize_start(item)["counts"], {"UNKNOWN": 1})

    def test_conflicting_start_compounds_are_unknown_and_duplicates_not_double_counted(
        self,
    ):
        item = race()
        item["data"]["stints"].append(dict(item["data"]["stints"][0]))
        self.assertEqual(summarize_start(item)["counts"], {"INTERMEDIATE": 1})
        item["data"]["stints"][-1]["compound"] = "HARD"
        self.assertEqual(summarize_start(item)["counts"], {"UNKNOWN": 1})

    def test_zero_lap_retirement_is_a_starter_but_stint_alone_is_not_proof(self):
        item = race("SOFT")
        item["data"]["laps"] = []
        item["data"]["session_result"][0].update(number_of_laps=0, dnf=True)
        self.assertEqual(summarize_start(item)["counts"], {"SOFT": 1})
        item["data"]["session_result"][0]["dnf"] = False
        result = summarize_start(item)
        self.assertEqual(result["starters"], 0)
        self.assertEqual(result["unconfirmed"], 1)

    def test_fixed_reference_image_is_replaced_even_without_image_file(self):
        item = race()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "year": item["session"]["year"],
                            "title": "그랑프리별 스타트 타이어",
                            "filename": "stale-image.png",
                            "kind": "starting-tyres",
                        }
                    ]
                )
            )
            page = render_race_attachments(item, root, starting_tyre_summaries={})
        self.assertIn('data-starting-tyres="openf1"', page)
        self.assertIn("I 1", page)
        self.assertNotIn("원본 파일 연결 대기", page)
        self.assertNotIn("data:image", page)

    def test_new_year_without_manifest_still_renders_dynamic_start_tyres(self):
        item = race()
        item["session"]["year"] += 1
        with tempfile.TemporaryDirectory() as folder:
            page = render_race_attachments(
                item, Path(folder), starting_tyre_summaries={}
            )
        self.assertIn("I 1", page)
        self.assertIn(str(item["session"]["year"]), page)

    def test_current_snapshot_overrides_old_summary_without_mutating_it(self):
        old = summarize_start(race("SOFT"))
        summaries = {old["session"]["session_key"]: old}
        page = render_starting_tyres(race(), summaries)
        self.assertIn("I 1", page)
        self.assertEqual(old["counts"], {"SOFT": 1})

    def test_earlier_race_in_archive_contains_later_race_start_tyres(self):
        first, last = race("SOFT"), race()
        year = first["session"]["year"]
        first["session"].update(
            session_key=101, meeting_key=1, date_start=f"{year}-03-01T12:00:00+00:00"
        )
        last["session"].update(
            session_key=202, meeting_key=2, date_start=f"{year}-11-08T12:00:00+00:00"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report.save_json(root / "weekend-1/data/101.json", first)
            report.save_json(root / "weekend-2/data/202.json", last)
            build_archive.build(root)
            html = (root / "index.html").read_text()
            entries = json.loads(
                html.split("const entries=", 1)[1].split(";const year=", 1)[0]
            )
        entry = next(x for x in entries if x["key"] == 101)
        page = gzip.decompress(base64.b64decode(entry["payload"])).decode()
        self.assertIn('data-start-session="202"', page)
        self.assertIn("I 1", page)


if __name__ == "__main__":
    unittest.main()
