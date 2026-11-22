import unittest
from race_overtakes import exchanges, render_overtakes


class OvertakeTests(unittest.TestCase):
    def snapshot(self, events):
        return {'session': {'session_name': 'Race', 'session_key': 1}, 'data': {'drivers': [{'driver_number': 1, 'full_name': '<One>', 'team_name': 'A'}, {'driver_number': 2, 'full_name': 'Two', 'team_name': 'B'}, {'driver_number': 3, 'full_name': 'Three', 'team_name': 'C'}], 'overtakes': events}}

    def event(self, a, b, second):
        return dict(session_key=1, overtaking_driver_number=a, overtaken_driver_number=b, date=f'2026-11-22T04:00:{second:02d}+00:00', position=1)

    def test_repasses_duplicates_and_uninvolved_drivers(self):
        first = self.event(1, 2, 1)
        s = self.snapshot([first, first, self.event(2, 1, 2), self.event(1, 2, 3)])
        self.assertEqual([e['repass'] for e in exchanges(s)], [False, True, True])
        page = render_overtakes(s)
        self.assertIn('순위 교환: 3건', page)
        self.assertIn('&lt;One&gt;', page)
        self.assertIn('Three', page)
        self.assertIn('피트스톱', page)

    def test_simultaneous_opposites_are_ambiguous(self):
        events = exchanges(self.snapshot([self.event(1, 2, 1), self.event(2, 1, 1)]))
        self.assertTrue(all(e['ambiguous'] and not e['repass'] for e in events))

    def test_missing_does_not_mean_zero_and_other_session_excluded(self):
        s = self.snapshot([dict(self.event(1, 2, 1), session_key=2)])
        self.assertEqual(exchanges(s), [])
        del s['data']['overtakes']
        self.assertIn('0회라는 뜻이 아닙니다', render_overtakes(s))
        s['session']['session_name'] = 'Qualifying'
        self.assertEqual(render_overtakes(s), '')
