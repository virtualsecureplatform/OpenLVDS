# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_tg2_four_bank_300_v1 as p
import test_four_bank_native_measure_300_v1 as fixtures


class FourBankPilotTests(unittest.TestCase):
    def test_actual_source_and_fresh_pair_wiring(self):
        m=json.loads((p.PARENT/'manifest.json').read_text());i=m['identity']
        library=(p.PARENT/p.SOURCE.VARIANT/'bank.spice').read_text()
        a,oa=p.fixture(p.ROOT/'build/unused-four-section-test',i,library,m['tasks'][0]['spec'],True)
        b,ob=p.fixture(p.ROOT/'build/unused-four-section-test',i,library,m['tasks'][0]['spec'],False)
        self.assertEqual(a.replace(p.SOURCE.numerical_trial.CARD+'\n',''),b)
        self.assertEqual(oa,ob);self.assertEqual(sum(len(o['devices']) for o in oa.values()),8224)

    def test_full_numerical_pair_and_failed_point_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);rows=[];helper=fixtures.FourSectionMeasureTests()
            for k in range(2):
                folder=out/str(k);folder.mkdir();obs,s=helper.fixture(folder)
                rows.append(dict(task=dict(id=str(k),centered=k==0,spec=s),error=None,
                                 result=p.metrology.measure(folder,obs,s)))
            pair=p.numerical_pair(out,rows,1,0)
            self.assertTrue(pair['passed']);self.assertTrue(p.pilot_passed(rows,pair))
            rows[1]['result']['sections']['section3']['terminal_stress'][0]['passed']=False
            self.assertFalse(p.numerical_pair(out,rows,1,0)['passed'])
            rows[0]['result']['four_section_transport_passed']=False
            self.assertFalse(p.pilot_passed(rows,pair))
            with self.assertRaises(ValueError):p.pilot_passed(rows[:1],pair)

    def test_native_execution_error_refuses_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);rows=[];helper=fixtures.FourSectionMeasureTests()
            for k in range(2):
                folder=out/str(k);folder.mkdir();obs,s=helper.fixture(folder)
                rows.append(dict(task=dict(id=str(k),centered=k==0,spec=s),error=None,
                                 result=p.metrology.measure(folder,obs,s)))
            rows[1]['error']='native failure'
            self.assertFalse(p.numerical_pair(out,rows,1,0)['passed'])
