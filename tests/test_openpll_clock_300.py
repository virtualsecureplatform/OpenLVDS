import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from openpll_clock_300 import metrics,policy
class Clock300Tests(unittest.TestCase):
    def test_new_band_accepts_300_and_rejects_old_400(self):
        for f,passed in [(290,True),(300,True),(310,True),(400,False)]:
            edges=np.column_stack((np.arange(32)*(1000/f/2),np.arange(32)%2))
            self.assertEqual(metrics(edges,policy.load()['requirements'])['passed'],passed)
    def test_non_alternating_or_untimed_edges_are_rejected(self):
        edges=np.column_stack((np.arange(32)*1.6667,np.arange(32)%2))
        for bad in [np.zeros_like(edges),edges[::-1]]:
            with self.assertRaises(ValueError):metrics(bad,policy.load()['requirements'])
