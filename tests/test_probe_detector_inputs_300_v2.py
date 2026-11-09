# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_detector_inputs_300_v2 as p


class DetectorPilotTests(unittest.TestCase):
    def test_full_boundary_pilot_and_native_binary_observations(self):
        specs=p.specifications();self.assertEqual(len(specs),36)
        self.assertEqual({(s['reference_slew_ps'],s['feedback_slew_ps']) for s in specs},{(20,250),(250,20),(250,250)})
        donor=json.loads((p.PARENT/'manifest.json').read_text());devices=p.observations.devices(p.PARENT,p.waveform.fixture(p.PARENT,specs[0],donor['tasks'][0]['devices']))
        self.assertTrue(any(d['name'].startswith('XB:') for d in devices))
        self.assertTrue(any(d['name'].startswith('XD:') for d in devices))
        for s in specs:
            self.assertEqual((s['process'],s['temperature']),('ss',40))
            text=p.wiring.fixture(p.ROOT/'build/unused-detector-pilot',s,devices)
            translated,names=p.runtime.translate(text)
            for n in ('r','f','rfast','ffast','rth','fth','pos','sw','xd.ha','xd.hb','xf.vcm'):
                self.assertIn('v('+n+')',names)
            self.assertIn('.options klu',translated)
            self.assertIn('.tran 1p 62n 0 1p',translated)
            with self.assertRaisesRegex(ValueError,'top-level hierarchy'):
                p.observations.devices(p.PARENT,text.replace('XB PB NB VDDIO 0 lvds_bias','',1))
            for d in devices:
                for n in d['terminals']:
                    if n not in ('0','VSS'):
                        n={'REF':'R','FDB':'F','REF_FAST':'RFAST','FDB_FAST':'FFAST','VDDD':'VDD'}.get(n,n)
                        self.assertIn('v('+n.replace(':','.').lower()+')',names)

    def test_complete_signed_brackets_and_native_success_required(self):
        rows=[dict(task=dict(id=str(k),spec=s),error=None,result=dict(source_point_passed=True)) for k,s in enumerate(p.specifications())]
        self.assertTrue(p.pilot_passed(rows))
        rows[0]['result']['source_point_passed']=False;self.assertFalse(p.pilot_passed(rows))
        rows[0]['result']=None;rows[0]['error']='native failure';self.assertFalse(p.pilot_passed(rows))
        with self.assertRaisesRegex(ValueError,'all 36'):p.pilot_passed(rows[:-1])
