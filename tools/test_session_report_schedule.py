import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import requests

from session_report_schedule import due_meeting, session_catalog
from weekend_report import save_json


class SessionScheduleTests(unittest.TestCase):
    def test_auth_restriction_uses_cached_schedule_but_server_errors_raise(self):
        response = requests.Response()
        response.status_code = 401
        error = requests.HTTPError(response=response)
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_json(root / 'catalog/sessions.json', [{'session_key': 1}])
            with patch('session_report_schedule.fetch', side_effect=error):
                self.assertEqual(session_catalog(root, now), [{'session_key': 1}])
                response.status_code = 500
                with self.assertRaises(requests.HTTPError):
                    session_catalog(root, now)

    def test_end_delay_retry_and_correction_checkpoints(self):
        end = datetime(2026, 11, 8, 19, tzinfo=timezone.utc)
        session = dict(session_name="Race", session_key=1, meeting_key=2, date_end=end.isoformat())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertIsNone(due_meeting([session], root, end + timedelta(minutes=29)))
            self.assertEqual(due_meeting([session], root, end + timedelta(minutes=30)), 2)
            path = root / "weekend-2/data/1.json"
            def saved(minutes):
                save_json(path, dict(fetched_at=(end + timedelta(minutes=minutes)).isoformat(),
                                    data={k: [1] for k in ("drivers", "laps", "session_result")}))
            saved(35)
            self.assertIsNone(due_meeting([session], root, end + timedelta(minutes=60)))
            self.assertEqual(due_meeting([session], root, end + timedelta(hours=2)), 2)
            saved(125)
            self.assertIsNone(due_meeting([session], root, end + timedelta(hours=3)))
            self.assertEqual(due_meeting([session], root, end + timedelta(hours=24)), 2)
            saved(1445)
            self.assertIsNone(due_meeting([session], root, end + timedelta(days=2)))
            path.write_text('{', encoding='utf-8')
            self.assertEqual(due_meeting([session], root, end + timedelta(days=2)), 2)
            self.assertIsNone(due_meeting([session], root, end + timedelta(days=8)))

    def test_cancelled_and_unsupported_sessions_do_not_trigger(self):
        now = datetime(2026, 11, 8, 20, tzinfo=timezone.utc)
        session = dict(session_name="Race", session_key=1, meeting_key=2,
                       date_end=(now - timedelta(hours=1)).isoformat(), is_cancelled=True)
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(due_meeting([session], Path(folder), now))
            session.update(is_cancelled=False, session_name="Sprint")
            self.assertIsNone(due_meeting([session], Path(folder), now))
