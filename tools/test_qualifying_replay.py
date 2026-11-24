import unittest
from qualifying_replay import timing_data


class QualifyingReplayTests(unittest.TestCase):
    def test_completed_laps_stay_in_own_phase_and_finish_after_flag(self):
        s={'session':{'session_name':'Qualifying'},'data':{'race_control':[
            {'qualifying_phase':1,'message':'SESSION STARTED','date':'2026-11-21T04:00:00+00:00'},
            {'qualifying_phase':1,'message':'SESSION FINISHED','date':'2026-11-21T04:18:00+00:00'},
            {'qualifying_phase':2,'message':'SESSION STARTED','date':'2026-11-21T04:27:00+00:00'},
            {'qualifying_phase':2,'message':'SESSION FINISHED','date':'2026-11-21T04:42:00+00:00'}],
            'laps':[{'driver_number':1,'lap_number':3,'date_start':'2026-11-21T04:17:30+00:00','lap_duration':90},
                    {'driver_number':2,'lap_number':4,'date_start':'2026-11-21T04:41:30+00:00','lap_duration':90},
                    {'driver_number':3,'lap_number':1,'date_start':'2026-11-21T04:28:00+00:00','lap_duration':180,'is_pit_out_lap':True}]}}
        data=timing_data(s)
        self.assertEqual([r[1] for r in data['laps']],[1,2])
        self.assertEqual(data['phases'][0][2],19*60)
        self.assertEqual(data['phases'][1][2],43*60)
        self.assertEqual(data['participants']['1'],[1])
        self.assertEqual(data['participants']['2'],[2,3])

    def test_missing_phase_is_not_invented(self):
        with self.assertRaises(ValueError):
            timing_data({'session':{'session_name':'Qualifying'},'data':{'race_control':[],'laps':[]}})


if __name__=='__main__':unittest.main()
