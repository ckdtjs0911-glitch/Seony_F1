import unittest
from race_gaps import gap_text


class GapTests(unittest.TestCase):
    def test_gap_uses_interval_not_leader_gap(self):
        self.assertEqual(gap_text({'interval':.823,'gap_to_leader':10.2}),'+0.823 s')
        self.assertEqual(gap_text({'interval':'+1 LAP'}),'+1 LAP')
        self.assertEqual(gap_text({'interval':None}),'—')
        self.assertEqual(gap_text({'interval':-1}),'—')
        self.assertEqual(gap_text(None),'—')
        self.assertEqual(gap_text(None,True),'선두')


if __name__=='__main__':unittest.main()
