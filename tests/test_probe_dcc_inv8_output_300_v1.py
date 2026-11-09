# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_inv8_output_300_v1 as p


class CompleteDCCPilotTests(unittest.TestCase):
    def test_declared_cases_and_exact_circuit_observation_extension(self):
        specs=p.specifications();self.assertEqual(specs,p.baseline.specifications())
        cells,hold,_=p.variant();library=cells+'\n'+hold
        self.assertEqual(len(specs),8)
        for s in specs:
            text,obs=p.wiring.fixture(p.ROOT/'build/unused-full-source-dcc',s,library)
            _,names=p.wiring.translate(text)
            self.assertEqual(len(obs['devices']),144);self.assertEqual(len(obs['passive_resistors']),2)
            self.assertIn('v(reset_n)',names);self.assertEqual(len(names),71)
            for d in obs['devices']+obs['passive_resistors']:
                for n in d['terminals']:
                    if n!='0':self.assertIn('v('+n.replace(':','.').lower()+')',names)

    def test_every_source_health_result_required_for_complete_pilot(self):
        rows=[dict(task=dict(id=str(k),spec=s),error=None,result=dict(source_screen_passed=True)) for k,s in enumerate(p.specifications())]
        self.assertTrue(p.pilot_passed(rows))
        rows[0]['result']['source_screen_passed']=False;self.assertFalse(p.pilot_passed(rows))
        rows[0]['result']=None;rows[0]['error']='native failed';self.assertFalse(p.pilot_passed(rows))
        with self.assertRaisesRegex(ValueError,'all eight INV8'):p.pilot_passed(rows[:-1])
