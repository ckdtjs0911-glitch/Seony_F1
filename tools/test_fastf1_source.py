import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from fastf1_source import identity_check,compare_laps,render_source


class FastF1SourceTests(unittest.TestCase):
    def snapshot(self):
        return {'session':{'year':2026,'location':'São Paulo','session_name':'Race','date_start':'2026-11-08T17:00:00+00:00','session_key':1,'meeting_key':2},'data':{
            'drivers':[{'driver_number':1,'name_acronym':'NOR'}],
            'laps':[{'driver_number':1,'lap_number':3,'lap_duration':90.001}]}}

    def test_identity_rejects_other_event_or_session(self):
        s=self.snapshot()
        identity_check(s,{'Location':'Sao Paulo'},'Race','2026-11-08T17:00:00+00:00')
        for location,name,date in [('Las Vegas','Race','2026-11-08T17:00:00+00:00'),('Sao Paulo','Qualifying','2026-11-08T17:00:00+00:00'),('Sao Paulo','Race','2025-11-08T17:00:00+00:00')]:
            with self.assertRaises(ValueError):identity_check(s,{'Location':location},name,date)

    def test_only_same_driver_identity_and_lap_are_compared(self):
        rows=[{'driver_number':'1','driver':'NOR','lap_number':3,'lap_time':90.004},
              {'driver_number':'1','driver':'VER','lap_number':3,'lap_time':80.0},
              {'driver_number':'1','driver':'NOR','lap_number':4,'lap_time':80.0}]
        result=compare_laps(self.snapshot(),rows)
        self.assertEqual(result['matched_laps'],1)
        self.assertEqual(result['differences_over_2ms'],1)
        self.assertEqual(result['unmatched_driver_numbers'],['1'])

    def test_failure_is_not_presented_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);d=root/'reports/weekend-2/media';d.mkdir(parents=True)
            (d/'1-fastf1-status.json').write_text('{"status":"unavailable"}')
            with patch('fastf1_source.ROOT',root):
                page=render_source(self.snapshot())
            self.assertIn('수집은 완료하지 못했습니다',page)
            self.assertNotIn('실제 수집 완료',page)

    def test_public_results_do_not_claim_telemetry_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);d=root/'reports/weekend-2/media';d.mkdir(parents=True)
            value={'session_key':1,'status':'results_only','comparison':{'matched_laps':0},'car_data':{},'results':[{'driverNumber':1}],
                   'identity':{'event':'Brazil GP','session':'Race'},'timing_auth_required':True,'fetched_at':'2026-11-25','library_commit':'abc123'}
            (d/'1-fastf1.json').write_text(json.dumps(value),encoding='utf-8')
            with patch('fastf1_source.ROOT',root):page=render_source(self.snapshot())
            self.assertIn('선수 결과 1명 조회 완료',page)
            self.assertIn('랩·텔레메트리 대조는 완료로 처리하지 않았으며',page)
            self.assertNotIn('실제 수집 완료',page)


if __name__=='__main__':unittest.main()
