# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolate_driver_balance as balance
from driver_current_variant import source_variant


class DriverBalanceControls(unittest.TestCase):
    def test_baseline_is_byte_identical_and_controls_replace_only_converter(self):
        source=source_variant((balance.ROOT/'analog/openlvds.spice').read_text())
        original='XLS D DP DN NB VDDIO VDDD VSS lvds_shift18_33_restore_64_24'
        self.assertEqual(balance.model(source,'baseline'),source)
        for case in balance.CASES[1:]:
            changed=balance.model(source,case)
            restored=re.sub(r'(?m)^VCONTROL_DP[^\n]+\nVCONTROL_DN[^\n]+',original,changed)
            self.assertEqual(restored,source)
            self.assertIn('XIT10 TOP PB VDDIO VDDIO',changed)

    def test_gate_waveforms_are_exact_complements_at_every_breakpoint(self):
        for ramp in [100,400]:
            def pairs(complement):
                return np.array([[float(t[:-1]),float(v)] for t,v in zip(*[iter(balance.stimulus(ramp,complement,3.3)[4:-1].split())]*2)])
            normal,inverted=pairs(False),pairs(True)
            np.testing.assert_array_equal(normal[:,0],inverted[:,0])
            np.testing.assert_allclose(normal[:,1]+inverted[:,1],3.3)
            self.assertAlmostEqual(normal[2,0]-normal[1,0],ramp/1000)

    def test_fixture_preserves_supplies_load_and_options(self):
        original='Test\n.include "/old/source.spice"\nVIO VDDIO 0 3.3\nVDIG VDDD 0 1.8\nVREF VREF 0 1.2\nIREF IREF 0 35u\nVD D 0 PWL(0 0 1900n 1.8)\nRT P N 100\nCP P 0 2p\nCN N 0 2p\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n.tran 5p 2540n 0 1n\n.print tran V(D) V(P) V(N)\n.end\n'
        actual=balance.fixture(original,Path('/old'),Path('/new'))
        for line in original.splitlines():
            if not line.startswith(('.include','VD D ','.tran','.print')):self.assertIn(line,actual)
        self.assertIn('.tran 1p 80n 0 1p',actual)
        with self.assertRaises(ValueError):balance.fixture(original.replace('2540n','2500n'),Path('/old'),Path('/new'))

    def test_measure_reports_complement_error_and_common_mode_extrema(self):
        t=np.linspace(0,80e-9,8001);diff=.3*np.sin(t*2*np.pi/2.5e-9);cm=1.2+.1*np.sin(t*2*np.pi/1.25e-9)
        dp=1.65+1.65*np.sin(t*2*np.pi/2.5e-9);dn=3.3-dp
        w=np.column_stack([np.arange(len(t)),t,np.zeros(len(t)),cm+diff/2,cm-diff/2,dp,dn,np.full(len(t),2.5),np.full(len(t),.5),np.full(len(t),1.3)])
        names=['D','P','N','XD:XCORE:DP','XD:XCORE:DN','XD:XCORE:TOP','XD:XCORE:BOT','XD:XCORE:SINK'];h={'V('+n+')':i+2 for i,n in enumerate(names)}
        result=balance.measure(w,h)
        self.assertAlmostEqual(result['common_mode_pp_v'],.2,places=4)
        self.assertAlmostEqual(result['complement_sum_error_max_v'],0)
        self.assertGreater(result['rising_output_edges'],20)
        self.assertEqual(len(result['extrema']),2)
        with self.assertRaises(ValueError):balance.measure(w[:-1],h)

    def test_unrelated_contexts_cannot_prepare_or_run(self):
        with self.assertRaises(ValueError):balance.prepare(Path('/tmp/other'))
        with self.assertRaises(ValueError):balance.run(Path('/tmp/other'))


if __name__=='__main__':unittest.main()
