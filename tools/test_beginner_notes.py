import unittest

import weekend_report as report
from test_weekend_report import snapshot


class BeginnerNotesTests(unittest.TestCase):
    def test_practice_uses_observed_time_and_escapes_names(self):
        page = report.render_beginner_notes('Practice 1', report.summarize(snapshot('Practice 1')))
        self.assertIn('Test &lt;Driver&gt;', page)
        self.assertIn('1:22.000', page)
        self.assertIn('연료량', page)

    def test_qualifying_separates_phase_records_from_final_order(self):
        page = report.render_beginner_notes('Qualifying', report.summarize(snapshot()))
        self.assertIn('Q1 제공 기록 중 최속', page)
        self.assertIn('1:20.300', page)
        self.assertIn('그리드 페널티', page)
        self.assertIn('같은 단계끼리', page)

    def test_race_explains_results_without_inventing_laps(self):
        page = report.render_beginner_notes('Race', report.summarize(snapshot('Race')))
        self.assertIn('결승 결과 1위', page)
        self.assertIn('DNF', page)
        self.assertNotIn('완료 랩 수는', page)

    def test_no_results_does_not_invent_a_winner(self):
        page = report.render_beginner_notes('Race', [])
        self.assertNotIn('결승 결과 1위는', page)
