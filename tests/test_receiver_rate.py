# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_analog import receiver_rate_metrics,REQ


class ReceiverBandwidth(unittest.TestCase):
    def waveform(self,scale=1.,period_scale=1.):
        t=np.arange(0,60e-9,5e-12)
        period=1e-6/max(REQ['clock_test_mhz'])
        pin=((t%period)<period/2).astype(float)
        q=1.8*scale*(((t-.6e-9)%(period_scale*period))<period_scale*period/2)
        return np.column_stack([np.arange(len(t)),t,1.075+.25*pin,1.325-.25*pin,q])

    def test_complete_rail_to_rail_clock_passes(self):
        self.assertTrue(receiver_rate_metrics(self.waveform())['passed'])

    def test_missing_edges_and_weak_high_level_are_rejected(self):
        self.assertFalse(receiver_rate_metrics(self.waveform(period_scale=2))['passed'])
        self.assertFalse(receiver_rate_metrics(self.waveform(scale=.7))['passed'])


if __name__=='__main__':unittest.main()
