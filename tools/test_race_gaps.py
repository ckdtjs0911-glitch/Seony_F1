import unittest
import tempfile
from pathlib import Path
from race_gaps import gap_text, enrich_pits


class GapTests(unittest.TestCase):
    def test_gap_uses_interval_not_leader_gap(self):
        self.assertEqual(gap_text({'interval':.823,'gap_to_leader':10.2}),'+0.823 s')
        self.assertEqual(gap_text({'interval':'+1 LAP'}),'+1 LAP')
        self.assertEqual(gap_text({'interval':None}),'—')
        self.assertEqual(gap_text({'interval':-1}),'—')
        self.assertEqual(gap_text(None),'—')
        self.assertEqual(gap_text(None,True),'선두')

    def test_pit_lap_is_recorded_without_inventing_lane(self):
        value={'start':0,'track':[[0,0],[10,0],[20,0]],'drivers':[{'number':1,'locations':[[0,0,0],[500,10,0],[1000,20,0]]}]}
        snapshot={'data':{'pit':[{'driver_number':1,'lap_number':1}], 'laps':[{'driver_number':1,'lap_number':1,'date_start':'1970-01-01T00:00:00+00:00','lap_duration':2}]}}
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'track.gz'
            self.assertTrue(enrich_pits(snapshot,value,target))
            self.assertEqual(value['drivers'][0]['pit_laps'],[[0,2000]])
            self.assertEqual(value['pit_tracks'],[])
            self.assertFalse(enrich_pits(snapshot,value,target))


if __name__=='__main__':unittest.main()
