"""Per-item sources are gathered at the end; caveats stay in the body."""
import gzip
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import weekend_report as report
from fastf1_source import fastf1_sources, render_source
from qualifying_replay import qualifying_sources, render_qualifying
from race_gaps import gap_sources, render_gaps
from report_video import render_section, video_sources
from test_weekend_report import snapshot

PIT_REFERENCE = {
    "segments": [[[0, 0], [1, 1]]],
    "source": ["https://www.openstreetmap.org/way/123"],
    "attribution": "© OpenStreetMap contributors · ODbL 1.0",
    "license": "https://www.openstreetmap.org/copyright",
    "outline_source": "https://github.com/bacinger/f1-circuits/blob/master/circuits/x.geojson",
}


def rendered(item):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "report.html"
        report.render([item], path)
        return path.read_text(encoding="utf-8")


def main_part(page):
    return page[page.index("<main>"): page.index("</main>")]


class SourceLayoutTests(unittest.TestCase):
    def test_sources_are_last_and_after_every_appendix(self):
        item = snapshot("Race")
        item["fetched_at"] = "2025-01-01T14:00:00+00:00"
        main = main_part(rendered(item))
        start = main.index('<section id="report-sources"')
        self.assertTrue(main.endswith("</section>"))
        self.assertEqual(main.count("<section", start), 1)
        for marker in ('id="race-pit-stops"', 'id="race-overtakes"', 'id="race-incidents"', "<h2>지표 해석과 한계</h2>"):
            self.assertIn(marker, main)
            self.assertLess(main.index(marker), start)
        body, sources = main[:start], main[start:]
        self.assertFalse("· 수집 시각" in body or "선택한 레이스 수집" in body or "출처:" in body, "source details left in body")
        self.assertIn('class="meta">test · session_key 1</p>', body)
        self.assertNotIn("api.openf1.org", body)
        self.assertIn("2025-01-01 14:00 UTC", sources)
        self.assertIn("v1/race_control?session_key=1", sources)
        self.assertIn("v1/overtakes?session_key=1", sources)
        self.assertIn("팀·선수별 피트스탑 기록", sources)
        # caveats stay in the body
        self.assertIn("실제 트랙 추월 총횟수는 이 데이터만으로 확정할 수 없습니다", body)

    def test_only_rendered_items_get_sources(self):
        main = main_part(rendered(snapshot("Qualifying")))
        sources = main[main.index('id="report-sources"'):]
        self.assertIn('data-source-session="퀄리파잉"', sources)
        for absent in ("레이스 주요 상황", "피트스탑", "오버테이크", "F1 COSMOS", "릴스", "OpenStreetMap", "FastF1", "시간별 퀄리파잉 위치"):
            self.assertNotIn(absent, sources)

    def test_weekend_sources_are_grouped_by_session(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.html"
            race = snapshot("Race")
            race["session"]["session_key"] = 3
            report.render([snapshot("Qualifying"), race], path)
            main = main_part(path.read_text(encoding="utf-8"))
        sources = main[main.index('id="report-sources"'):]
        self.assertLess(sources.index('data-source-session="퀄리파잉"'), sources.index('data-source-session="레이스"'))
        self.assertIn("session_key=3", sources)


class ModuleSourceTests(unittest.TestCase):
    def test_gap_map_credit_and_reference_limits_move_to_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            value = {"session_key": 1, "fetched_at": "2025-01-01T14:00:00+00:00", "pit_reference": PIT_REFERENCE, "drivers": []}
            (directory / "1-track.json.gz").write_bytes(gzip.compress(json.dumps(value).encode()))
            item = snapshot("Race")
            body = render_gaps(item, directory)
            entries = " ".join(gap_sources(item, directory))
        self.assertNotIn("openstreetmap.org", body)
        self.assertNotIn("f1cosmos", body)
        self.assertIn("실제 피트 이동 궤적과는 구분합니다", body)
        self.assertIn("© OpenStreetMap contributors · ODbL 1.0", entries)
        self.assertIn("way/123", entries)
        self.assertIn("bacinger/f1-circuits</a> · MIT", entries)
        self.assertIn("직접 검증하지 못했습니다", entries)

    def test_qualifying_replay_keeps_completed_lap_caveat(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            value = {"session_key": 1, "complete": True, "fetched_at": "2025-01-01T14:00:00+00:00", "pit_reference": PIT_REFERENCE, "drivers": [{"locations": [[0, 1, 2]]}]}
            (directory / "1-qualifying.json.gz").write_bytes(gzip.compress(json.dumps(value).encode()))
            item = snapshot("Qualifying")
            body = render_qualifying(item, directory)
            entries = " ".join(qualifying_sources(item, directory))
        self.assertIn("기록은 랩 완료 뒤 반영하며", body)
        self.assertIn("실제 차량 궤적과는 구분합니다", body)
        self.assertNotIn("openstreetmap.org", body)
        self.assertNotIn("출처:", body)
        self.assertIn("OpenStreetMap", entries)
        self.assertIn("v1/location?session_key=1", entries)

    def test_video_reel_limit_moves_to_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "12-videos.json").write_text(json.dumps({"session_key": 12, "fetched_at": "2025-01-01T14:00:00+00:00", "videos": [{"file": "a.mp4", "title": "t", "description": "d"}]}), encoding="utf-8")
            (root / "a.mp4").write_bytes(b"mp4")
            item = {"session": {"session_key": 12, "session_name": "Race"}}
            body = render_section(item, root)
            entries = " ".join(video_sources(item, root))
        self.assertIn("MP4 영상 다운로드", body)
        self.assertNotIn("instagram", body)
        self.assertNotIn("출처:", body)
        self.assertIn("instagram.com/reel", entries)
        self.assertIn("영상 화면은 확인하지 못했습니다", entries)

    def test_fastf1_401_stays_in_body_and_details_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "reports/weekend-2/media"
            media.mkdir(parents=True)
            value = {"session_key": 1, "status": "results_only", "comparison": {"matched_laps": 0}, "car_data": {}, "results": [{"driverNumber": 1}],
                     "identity": {"event": "Brazil GP", "session": "Race"}, "timing_auth_required": True, "timing_http_status": 401,
                     "fetched_at": "2026-11-25T01:00:00+00:00", "library_commit": "abcdef1234567890", "library_version": "3.9"}
            (media / "1-fastf1.json").write_text(json.dumps(value), encoding="utf-8")
            item = snapshot("Race")
            with patch("fastf1_source.ROOT", root):
                body = render_source(item)
                entries = " ".join(fastf1_sources(item))
        self.assertIn("F1 TV 인증을 요구해 조회를 보류했습니다", body)
        self.assertIn("선수 결과 1명 조회 완료", body)
        self.assertNotIn("docs.fastf1.dev", body)
        self.assertNotIn("abcdef123456", body)
        self.assertIn("HTTP 401 · 인증 대기", entries)
        self.assertIn("Ergast/Jolpica", entries)
        self.assertIn("abcdef123456", entries)
        self.assertNotRegex(entries, re.compile("수집 완료"))
        value.update(status="schedule_only", results=[])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "reports/weekend-2/media"
            media.mkdir(parents=True)
            (media / "1-fastf1.json").write_text(json.dumps(value), encoding="utf-8")
            with patch("fastf1_source.ROOT", root):
                entries = " ".join(fastf1_sources(item))
        self.assertIn("공개 일정", entries)
        self.assertNotIn("공개 결과", entries)


    def test_missing_attachment_is_not_cited_and_shown_races_are(self):
        from race_attachments import attachment_sources, render_race_attachments
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "manifest.json").write_text(json.dumps([{"year": 2025, "title": "없는 그림", "filename": "missing.png", "source": "사용자 제공 참고자료"}]), encoding="utf-8")
            item = snapshot("Race")
            page = render_race_attachments(item, directory, starting_tyre_summaries={})
            found = dict(attachment_sources(item, page, directory))
        self.assertIn("원본 파일 연결 대기", page)
        self.assertNotIn("없는 그림", found)
        self.assertIn("표에 집계된 레이스 1개", " ".join(found["그랑프리별 스타트 타이어"]))


if __name__ == "__main__":
    unittest.main()
