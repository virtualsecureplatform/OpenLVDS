# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_compact_driver_loop as observer


class CompactDriverObservationOnly(unittest.TestCase):
    DECK='''.include "/old/source.spice"
VIO VDDIO 0 3.3
VDIG VDDD 0 1.8
IREF IREF 0 35u
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 1p 80n 0 1p
.print tran V(D) V(P) V(N)
.save i(VIO) i(VDIG)
.end
'''
    def test_only_include_and_observations_change(self):
        rows=[dict(device=('XD:XCORE:' if i<302 else 'XD:XB:')+str(i),terminals=dict(D='0',G='0',S='0',B='0')) for i in range(305)]
        with patch.object(observer.stress,'terminal_observations',return_value=rows),patch.object(observer,'ProbeNetwork'):
            deck,probes,_=observer.fixture(self.DECK,Path('/old'),Path('/new'),'same model',dict(CM=dict(native_node='sense')))
        strip=lambda s:[x for x in s.splitlines() if not re.match(r'^\.(include|print|save)\b',x)]
        self.assertEqual(strip(deck),strip(self.DECK))
        self.assertIn('.save i(VIO) i(VDIG)',deck)
        self.assertEqual(probes['CM'],'XD:XCORE:sense')
        self.assertEqual(probes['NB'],'XD:NB')

    def test_partial_or_looser_fixture_rejected_before_observation(self):
        for deck in [self.DECK.replace('80n','40n'),self.DECK.replace('0 1p','0 20p'),self.DECK.replace('V(N)','V(OTHER)')]:
            with self.assertRaises(ValueError):observer.fixture(deck,Path('/old'),Path('/new'),'same model',{})
