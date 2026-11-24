import gzip
import json
import tempfile
import unittest
from pathlib import Path
from compare_player import collect_player, render_player


class PlayerTests(unittest.TestCase):
    def fixture(self):
        return {'session': {'session_name':'Race','session_key':12}, 'data': {
            'drivers':[{'driver_number':1,'full_name':'A <name>'},{'driver_number':2,'full_name':'B'}],
            'laps':[{'driver_number':d,'lap_number':1,'date_start':'2026-11-22T04:00:00+00:00','lap_duration':90} for d in (1,2)]}}

    def test_collect_validate_cache_and_non_race(self):
        s=self.fixture();calls=[]
        def fetch(endpoint, params):
            calls.append(params)
            return [{'session_key':12,'driver_number':params['driver_number'],'date':'2026-11-22T04:00:00+00:00','speed':123,'brake':100,'drs':None}]
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            self.assertTrue(collect_player(s,p,fetch))
            self.assertFalse(collect_player(s,p,fetch))
            self.assertEqual(len(calls),2)
            data=json.loads(gzip.decompress((p/'12-compare.json.gz').read_bytes()))
            self.assertEqual(data['drivers'][0]['rows'][0],[0,123,None,100,None,None])
            self.assertIn('replay-a',render_player(s,p))
            s['session']['session_name']='Qualifying'
            self.assertEqual(render_player(s,p),'')
            self.assertFalse(collect_player(s,p,fetch))

    def test_mismatched_driver_is_not_displayed(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            collect_player(self.fixture(),p,lambda *a:[{'session_key':99,'driver_number':999}])
            data=json.loads(gzip.decompress((p/'12-compare.json.gz').read_bytes()))
            self.assertTrue(all(not x['rows'] and x['error']=='ValueError' for x in data['drivers']))


if __name__=='__main__':unittest.main()
