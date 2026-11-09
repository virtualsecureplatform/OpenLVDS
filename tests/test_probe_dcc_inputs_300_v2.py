# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_inputs_300_v2 as p


class CorrectedDCCPilotTests(unittest.TestCase):
    def test_complete_pilot_and_actual_native_runner_translation(self):
        specs=p.specifications();self.assertEqual(len(specs),8)
        self.assertEqual({(s['r_duty'],s['f_duty']) for s in specs},{(.4,.4),(.6,.6)})
        self.assertEqual({(s['r_slew_10_90_ps'],s['f_slew_10_90_ps']) for s in specs},{(20,20),(250,250),(20,250),(250,20)})
        for s in specs:
            p.waveform.check(s);self.assertEqual((s['process'],s['temperature'],s['mhz'],s['phase_error_ps']),('sf',40,310,0))
            deck=p.waveform.fixture(p.ROOT/'build/unused-corrected-dcc-pilot',s)
            translated,names=p.runtime.translate(deck)
            self.assertIn('v(xd.areset)',names);self.assertIn('v(xd.breset)',names)
            self.assertIn('v(p0)',names);self.assertIn('v(p180)',names)
            self.assertIn('.options klu',translated)

    def test_every_native_point_and_physical_verdict_required(self):
        rows=[dict(task=dict(id=str(k),spec=s),error=None,result=dict(source_screen_passed=True)) for k,s in enumerate(p.specifications())]
        self.assertTrue(p.pilot_passed(rows));rows[0]['result']['source_screen_passed']=False;self.assertFalse(p.pilot_passed(rows))
        rows[0]['result']=None;rows[0]['error']='native integration failed';self.assertFalse(p.pilot_passed(rows))
        with self.assertRaisesRegex(ValueError,'all eight'):p.pilot_passed(rows[:-1])
