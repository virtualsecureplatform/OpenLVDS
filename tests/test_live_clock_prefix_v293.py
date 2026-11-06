# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_live_clock_prefix_v293 as p

class LiveClockPrefixTests(unittest.TestCase):
    def spec(self):return dict(coarse=0,fine=0,frequency_mhz=410,duty=.5,cycles=8)

    def waveform(self,delay):
        t=np.arange(0,24e-9,2e-12);period=1e-6/410
        def signal(shift):
            return sum(.9*(np.tanh((t-2.1e-9-k*period-shift)/45e-12)-np.tanh((t-2.1e-9-(k+.5)*period-shift)/45e-12)) for k in range(8))
        return np.column_stack((t,signal(0),signal(delay)))

    def test_observed_necessary_quarter_failure_cannot_admit_incomplete_native_trace(self):
        r=p.analyze(self.waveform(850e-12),self.spec())
        self.assertTrue(r['observed_zero_quarter_budget_violation'])
        self.assertAlmostEqual(r['observed_timing']['zero_code_fast_quarter_headroom_ps'],1e6/410/4-850,places=2)
        for key in ('completed_transport_admitted','complete_native_terminal_safety_checked','source_waveform_complete','qualified_phy'):
            self.assertFalse(r[key])

    def test_positive_headroom_and_missing_future_events_never_admit_native_transport(self):
        values=self.waveform(500e-12);r=p.analyze(values,self.spec())
        self.assertFalse(r['observed_zero_quarter_budget_violation']);self.assertGreater(r['observed_timing']['zero_code_fast_quarter_headroom_ps'],100)
        self.assertFalse(r['completed_transport_admitted'])
        r=p.analyze(values[:1000],self.spec());self.assertFalse(r['observed_timing']['all_input_output_pulses_present']);self.assertFalse(r['observed_zero_quarter_budget_violation'])

    def test_nonfinite_missing_startup_nonmonotonic_or_wrong_columns_are_rejected(self):
        values=self.waveform(500e-12)
        for bad in (values[1:],values[:,1:],values[::-1],np.full((5,3),np.nan)):
            with self.assertRaises(ValueError):p.analyze(bad,self.spec())

    def test_retained_original_and_n16_zero_prefixes_reproduce_without_admission(self):
        base=p.ROOT/'build/reports/live_clock_prefix_v293/20261106T153315Z'
        if not base.exists():self.skipTest('Retained native clock prefixes required')
        for pid,headroom in ((1990963,-265.8380171271249),(2005259,-205.62898213614994)):
            folder=base/str(pid);r=json.loads((folder/'observation.json').read_text())
            self.assertEqual(p.live.sha((folder/'time_in_out.tsv').read_bytes()),r['selected_vectors_sha256'])
            self.assertEqual(p.live.sha((folder/'header.bin').read_bytes()),r['source_prefix']['header_sha256'])
            self.assertEqual(p.live.sha((p.ROOT/r['manifest']).read_bytes()),r['manifest_sha256'])
            values=np.loadtxt(folder/'time_in_out.tsv');measured=p.analyze(values,r['task']['spec'])
            self.assertTrue(measured['observed_zero_quarter_budget_violation'])
            self.assertFalse(measured['completed_transport_admitted'])
            self.assertAlmostEqual(measured['observed_timing']['zero_code_fast_quarter_headroom_ps'],headroom,places=6)
            for edge in ('rise','fall'):
                self.assertEqual(len(measured['observed_timing']['edge_delays_ps'][edge]),8)
                np.testing.assert_allclose(measured['observed_timing']['edge_delays_ps'][edge],r['observed_timing']['edge_delays_ps'][edge],rtol=0,atol=1e-6)

if __name__=='__main__':unittest.main()
