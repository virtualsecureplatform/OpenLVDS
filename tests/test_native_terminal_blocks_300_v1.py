# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import itertools
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_terminal_blocks_300_v1 as p


class TerminalBlockTests(unittest.TestCase):
    def fixture(self):
        rng=np.random.default_rng(1642)
        names=['time']+['v(n'+str(k)+')' for k in range(12)]
        wave=rng.normal(size=(301,len(names)));wave[:,0]=np.arange(len(wave))
        devices=[dict(name='M'+str(k),terminals=['n'+str((k+j)%12) if j!=3 else '0' for j in range(4)],limit_v=1.95) for k in range(9)]
        return names,wave,devices

    def reference(self,names,wave,devices):
        ground=np.zeros(len(wave));result=[]
        for d in devices:
            v=[ground if n=='0' else wave[:,names.index('v('+n+')')] for n in d['terminals']]
            peak=max(float(np.abs(a-b).max()) for a,b in itertools.combinations(v,2))
            result.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
        return result

    def test_exact_pairwise_equivalence_and_input_immutability_across_block_sizes(self):
        names,wave,devices=self.fixture();before=wave.copy();expected=self.reference(names,wave,devices)
        for block in (1,7,64,301,512):
            self.assertEqual(p.envelopes(names,wave,devices,block_rows=block),expected)
            np.testing.assert_array_equal(wave,before)

    def test_dc_and_last_sample_peaks_and_ground_never_discarded(self):
        names=['time','v(a)','v(b)'];wave=np.zeros((301,3));wave[:,0]=1000
        wave[0,1]=1.95;wave[-1,2]=np.nextafter(1.95,np.inf)
        devices=[dict(name='M0',terminals=['a','0','0','0'],limit_v=1.95),
                 dict(name='M1',terminals=['b','0','0','0'],limit_v=1.95)]
        out=p.envelopes(names,wave,devices)
        self.assertEqual(out[0]['maximum_terminal_difference_v'],1.95);self.assertTrue(out[0]['passed'])
        self.assertEqual(out[1]['maximum_terminal_difference_v'],wave[-1,2]);self.assertFalse(out[1]['passed'])

    def test_invalid_maps_samples_and_limits_are_refused(self):
        names,wave,devices=self.fixture()
        for block in (0,-1,True,1.5):
            with self.assertRaises(ValueError):p.envelopes(names,wave,devices,block_rows=block)
        for bad in (float('nan'),float('inf')):
            changed=wave.copy();changed[0,1]=bad
            with self.assertRaisesRegex(ValueError,'Nonfinite'):p.envelopes(names,changed,devices)
        changed=deepcopy(devices);changed[0]['terminals'][0]='missing'
        with self.assertRaisesRegex(ValueError,'Missing actual'):p.envelopes(names,wave,changed)
        with self.assertRaises(ValueError):p.envelopes(names,wave,[])
