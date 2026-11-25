"""Automatic gate: KST Friday-Monday, 3-4 h after the end, local files only, one attempt per session."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import requests

import report_attempts
import session_report_schedule as gate
import weekend_report as report
from weekend_report import save_json

KST = timezone(timedelta(hours=9))
# Saturday 2026-11-28 12:00 KST
SATURDAY_END = datetime(2026, 11, 28, 12, tzinfo=KST)


def session(key=1, end=SATURDAY_END, **extra):
    value = dict(session_name="Race", session_key=key, meeting_key=2,
                 date_start=(end - timedelta(hours=2)).isoformat(), date_end=end.isoformat())
    value.update(extra)
    return value


def no_network():
    error = AssertionError("external call during local schedule check")
    return (patch("requests.sessions.Session.request", side_effect=error),
            patch.object(report, "fetch", side_effect=error),
            patch.object(report.openf1_client, "get", side_effect=error))


class GateTests(unittest.TestCase):
    def test_cloud_restart_gate_boundary_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "pause.json"
            resume = datetime(2026, 11, 28, 0, 0, tzinfo=KST)
            save_json(config, {"resume_at": resume.isoformat()})
            a, b, c = no_network()
            with a as http, b, c:
                self.assertFalse(gate.automatic_resumed(resume - timedelta(seconds=1), config))
                self.assertTrue(gate.automatic_resumed(resume, config))
                self.assertTrue(gate.automatic_resumed(resume.astimezone(timezone.utc), config))
                for value in ({}, {"resume_at": "invalid"}, {"resume_at": "2026-11-28T00:00:00"}):
                    save_json(config, value)
                    self.assertFalse(gate.automatic_resumed(resume, config))
                self.assertFalse(gate.automatic_resumed(resume, Path(folder) / "missing"))
                http.assert_not_called()

    def test_paused_scheduled_main_never_reads_sessions_or_calls_network(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "pause.json"
            save_json(config, {"resume_at": "2099-01-01T00:00:00+09:00"})
            out = io.StringIO()
            a, b, c = no_network()
            with a, b, c, patch.object(gate, "session_catalog") as catalog, \
                    patch("sys.argv", ["gate", "--pause-config", str(config)]), \
                    patch.dict(os.environ, {"GITHUB_OUTPUT": ""}), redirect_stdout(out):
                gate.main()
            catalog.assert_not_called()
            self.assertEqual(out.getvalue(), "run=false\nmeeting=\nsessions=\n")

    def due(self, sessions, now, root):
        return gate.due_sessions(sessions, root, now)

    def test_three_to_four_hour_window_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            item = session()
            for offset, expected in [
                (timedelta(hours=2, minutes=59), []),
                (timedelta(hours=3), [1]),
                (timedelta(hours=3, minutes=59), [1]),
                (timedelta(hours=4), []),
            ]:
                self.assertEqual(self.due([item], SATURDAY_END + offset, root)[1], expected, offset)

    def test_kst_friday_to_monday_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cases = [
                (datetime(2026, 11, 27, 0, 0, tzinfo=KST), True),    # Fri 00:00 KST = Thu 15:00 UTC
                (datetime(2026, 11, 26, 23, 59, tzinfo=KST), False),  # Thu 23:59 KST
                (datetime(2026, 11, 30, 23, 59, tzinfo=KST), True),   # Mon 23:59 KST = Mon 14:59 UTC
                (datetime(2026, 12, 1, 0, 0, tzinfo=KST), False),     # Tue 00:00 KST = Mon 15:00 UTC
                (datetime(2026, 12, 2, 12, 0, tzinfo=KST), False),    # Wed
            ]
            for now, expected in cases:
                item = session(end=now - timedelta(hours=3))
                self.assertEqual(gate.automatic_day(now.astimezone(timezone.utc)), expected, now)
                self.assertEqual(bool(self.due([item], now.astimezone(timezone.utc), root)[1]), expected, now)

    def test_actual_end_beats_scheduled_end(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            actual = SATURDAY_END + timedelta(minutes=50)
            item = session(actual_date_end=actual.isoformat())
            self.assertEqual(self.due([item], SATURDAY_END + timedelta(hours=3), root)[1], [])
            self.assertEqual(self.due([item], actual + timedelta(hours=3), root)[1], [1])

    def test_cancelled_and_unsupported_sessions_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = SATURDAY_END + timedelta(hours=3)
            self.assertEqual(self.due([session(is_cancelled=True)], now, root), (None, []))
            self.assertEqual(self.due([session(session_name="Testing")], now, root), (None, []))

    def test_attempted_or_processed_sessions_are_not_queried_again(self):
        now = SATURDAY_END + timedelta(hours=3, minutes=15)
        for status in ("started", "auth_restricted", "missing", "failed", "unchanged", "collected"):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                report_attempts.record(root, session(), status, SATURDAY_END + timedelta(hours=3))
                self.assertEqual(self.due([session()], now, root), (None, []), status)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_json(root / "weekend-2/data/1.json", dict(
                fetched_at=(SATURDAY_END + timedelta(hours=3, minutes=5)).isoformat(),
                data={k: [1] for k in ("drivers", "laps", "session_result")}))
            self.assertEqual(self.due([session()], now, root), (None, []))

    def test_deferred_attempt_waits_for_recorded_later_end(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            later = SATURDAY_END + timedelta(minutes=40)
            report_attempts.record(root, session(), "deferred_end_later", SATURDAY_END + timedelta(hours=3), actual_end=later)
            self.assertEqual(self.due([session()], SATURDAY_END + timedelta(hours=3, minutes=20), root)[1], [])
            self.assertEqual(self.due([session()], later + timedelta(hours=3), root)[1], [1])

    def test_only_due_sessions_of_one_meeting_are_listed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            items = [session(1), session(3, end=SATURDAY_END - timedelta(hours=2)), session(4, end=SATURDAY_END + timedelta(minutes=10))]
            self.assertEqual(self.due(items, SATURDAY_END + timedelta(hours=3, minutes=20), root), (2, [1, 4]))

    def test_local_catalog_only_and_zero_network_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_json(root / "catalog/sessions.json", [session(1), session(9, end=SATURDAY_END - timedelta(days=1))])
            newer = session(1, end=SATURDAY_END + timedelta(minutes=30))
            save_json(root / "weekend-2/sessions.json", [newer])
            a, b, c = no_network()
            with a as http, b, c:
                catalog = {s["session_key"]: s for s in gate.session_catalog(root)}
                self.assertEqual(catalog[1]["date_end"], newer["date_end"])
                self.assertEqual(self.due(list(catalog.values()), SATURDAY_END + timedelta(hours=3), root), (None, []))
                # weekday outside Friday-Monday: still no external call
                self.assertEqual(self.due(list(catalog.values()), datetime(2026, 12, 2, 3, tzinfo=timezone.utc), root), (None, []))
                http.assert_not_called()

    def test_main_prints_session_list_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_json(root / "catalog/sessions.json", [session(1)])
            now = SATURDAY_END + timedelta(hours=3, minutes=1)
            out, output = io.StringIO(), root / "github-output"

            class Clock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return now.astimezone(tz)

            a, b, c = no_network()
            with a, b, c, patch.object(gate, "datetime", Clock), patch("sys.argv", ["gate", "--reports", str(root)]), \
                    patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), redirect_stdout(out):
                gate.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "run=true\nmeeting=2\nsessions=1\n")


class TargetedCollectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.now = SATURDAY_END + timedelta(hours=3, minutes=5)
        self.practice = session(1, end=SATURDAY_END - timedelta(days=1), session_name="Practice 1")
        self.race = session(5)
        self.cached = {"session": self.practice, "status": "cached", "fetched_at": "2026-11-27T00:00:00+00:00",
                       "data": {"drivers": [1], "laps": [1], "session_result": [1]}}
        save_json(self.root / "weekend-2/data/1.json", self.cached)
        self.calls = []

    def tearDown(self):
        self.folder.cleanup()

    def fetch_with(self, data, metadata=None):
        def fetch(endpoint, params):
            self.calls.append((endpoint, params.get("session_key", params.get("meeting_key"))))
            if endpoint == "sessions":
                return metadata or [self.practice, self.race]
            return data(endpoint)
        return fetch

    def attempt(self, key=5):
        return report_attempts.load(self.root)[str(key)]

    def test_only_target_session_is_fetched_and_others_stay_cached(self):
        rows = {"drivers": [{"driver_number": 1}], "laps": [{"driver_number": 1, "lap_number": 1}], "session_result": [{"driver_number": 1}]}
        with patch.object(report, "fetch", side_effect=self.fetch_with(lambda e: rows.get(e, []))), patch.object(report, "render"):
            self.assertEqual(report.collect(2, self.root, [5], now=self.now), 0)
        self.assertEqual({key for _, key in self.calls if key != 2}, {5})
        self.assertNotIn(("laps", 1), self.calls)
        self.assertEqual(json.loads((self.root / "weekend-2/data/1.json").read_text(encoding="utf-8")), self.cached)
        self.assertEqual((self.attempt()["status"], self.attempt()["completed"]), ("collected", True))
        self.assertNotIn("1", report_attempts.load(self.root))

    def test_unchanged_target_records_state_without_rendering(self):
        rows = {"drivers": [1], "laps": [1], "session_result": [1]}
        save_json(self.root / "weekend-2/data/5.json", {"session": self.race, "fetched_at": "x", "data": dict(rows, stints=[], pit=[], race_control=[])})
        (self.root / "weekend-2/weekend-report.html").write_text("keep", encoding="utf-8")
        with patch.object(report, "fetch", side_effect=self.fetch_with(lambda e: rows.get(e, []))), patch.object(report, "render") as render:
            self.assertEqual(report.collect(2, self.root, [5], now=self.now), 2)
            render.assert_not_called()
        self.assertEqual((self.root / "weekend-2/weekend-report.html").read_text(encoding="utf-8"), "keep")
        self.assertEqual(self.attempt()["status"], "unchanged")

    def test_401_and_missing_are_recorded_but_not_completed(self):
        response = requests.Response()
        response.status_code = 401

        def denied(endpoint):
            raise requests.HTTPError(response=response)

        with patch.object(report, "fetch", side_effect=self.fetch_with(denied)), patch.object(report, "render") as render:
            with self.assertRaises(requests.HTTPError):
                report.collect(2, self.root, [5], now=self.now)
            render.assert_not_called()
        self.assertEqual((self.attempt()["status"], self.attempt()["completed"]), ("auth_restricted", False))
        self.assertEqual(gate.due_sessions([self.race], self.root, self.now + timedelta(minutes=15)), (None, []))
        os.remove(report_attempts.path_for(self.root))
        with patch.object(report, "fetch", side_effect=self.fetch_with(lambda e: [])), patch.object(report, "render"):
            self.assertEqual(report.collect(2, self.root, [5], now=self.now), 1)
        self.assertEqual((self.attempt()["status"], self.attempt()["completed"]), ("missing", False))

    def test_attempt_is_kept_when_the_run_crashes(self):
        with patch.object(report, "fetch", side_effect=RuntimeError("crash")):
            with self.assertRaises(RuntimeError):
                report.collect(2, self.root, [5], now=self.now)
        self.assertEqual((self.attempt()["status"], self.attempt()["completed"]), ("started", False))

    def test_later_actual_end_preserves_data_and_defers(self):
        later = dict(self.race, actual_date_end=(SATURDAY_END + timedelta(minutes=30)).isoformat())
        with patch.object(report, "fetch", side_effect=self.fetch_with(lambda e: self.fail("early data fetch"), [self.practice, later])), \
                patch.object(report, "render"):
            report.collect(2, self.root, [5], now=self.now)
        self.assertEqual([c for c in self.calls if c[0] != "sessions"], [])
        self.assertFalse((self.root / "weekend-2/data/5.json").exists())
        self.assertEqual(self.attempt()["status"], "deferred_end_later")
        self.assertEqual(gate.due_sessions([self.race], self.root, self.now + timedelta(minutes=10)), (None, []))
        self.assertEqual(gate.due_sessions([self.race], self.root, SATURDAY_END + timedelta(hours=3, minutes=30))[1], [5])

    def test_manual_collect_without_targets_keeps_full_behaviour(self):
        rows = {"drivers": [1], "laps": [1], "session_result": [1]}
        with patch.object(report, "fetch", side_effect=self.fetch_with(lambda e: rows.get(e, []))), patch.object(report, "render"):
            report.collect(2, self.root, now=self.now)
        self.assertIn(("laps", 1), self.calls)
        self.assertIn(("laps", 5), self.calls)
        self.assertFalse(report_attempts.path_for(self.root).exists())

    def test_deferred_only_run_does_not_render_or_publish(self):
        later = dict(self.race, actual_date_end=(SATURDAY_END + timedelta(minutes=30)).isoformat())
        self.assertFalse((self.root / "weekend-2/weekend-report.html").exists())
        with patch.object(report, "fetch", side_effect=self.fetch_with(lambda e: [], [self.practice, later])), \
                patch.object(report, "render") as render:
            self.assertEqual(report.collect(2, self.root, [5], now=self.now), 2)
            render.assert_not_called()

    def test_supplementary_steps_only_process_selected_sessions(self):
        import fastf1_source
        import qualifying_replay
        import report_video
        fresh = datetime.now(timezone.utc).isoformat()
        for key in (5, 6):
            save_json(self.root / f"weekend-2/data/{key}.json", {
                "session": session(key, session_name="Qualifying"), "fetched_at": fresh, "data": {"laps": [1]}})
        seen = []
        with patch("sys.argv", ["report_video.py", "--root", str(self.root), "--sessions", "5"]), \
                patch.object(qualifying_replay, "collect_qualifying", side_effect=lambda s, *a: seen.append(("video", s["session"]["session_key"])) or False):
            report_video.main()
        with patch("sys.argv", ["fastf1_source.py", "--root", str(self.root), "--sessions", "5"]), \
                patch.object(fastf1_source, "collect", side_effect=lambda s, *a: seen.append(("fastf1", s["session"]["session_key"])) or False):
            fastf1_source.main()
        self.assertEqual(sorted(seen), [("fastf1", 5), ("video", 5)])

    def test_state_only_merge_keeps_newest_and_never_marks_unpublished_data_complete(self):
        base = {"1": {"status": "collected", "completed": True, "updated_at": "2026-11-28T03:00:00+00:00"},
                "7": {"status": "auth_restricted", "completed": False, "updated_at": "2026-11-28T05:00:00+00:00"}}
        ours = {"5": {"status": "collected", "completed": True, "updated_at": "2026-11-28T06:05:00+00:00"},
                "7": {"status": "started", "completed": False, "updated_at": "2026-11-28T04:00:00+00:00"}}
        merged = report_attempts.merge(base, ours, unpublished=["5"])
        self.assertEqual(set(merged), {"1", "5", "7"})
        self.assertEqual(merged["7"]["status"], "auth_restricted")
        self.assertEqual((merged["5"]["status"], merged["5"]["completed"]), ("not_published", False))
        self.assertEqual(merged["1"]["status"], "collected")
        self.assertEqual(gate.due_sessions([self.race], self.root, self.now), (2, [5]))
        report_attempts.path_for(self.root).parent.mkdir(parents=True, exist_ok=True)
        report_attempts.path_for(self.root).write_text(json.dumps(merged), encoding="utf-8")
        self.assertEqual(gate.due_sessions([self.race], self.root, self.now), (None, []))


if __name__ == "__main__":
    unittest.main()
