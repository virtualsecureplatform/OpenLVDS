# SPDX-License-Identifier: GPL-3.0-only
import itertools
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_source_300 as target


class Source300Tests(unittest.TestCase):
    def test_complete_profile_matrix(self):
        specs=target.specifications()
        actual={tuple(s[k] for k in ['process','temperature','mhz','duty','slew_ps','phase_error_ps']) for s in specs}
        expected=set(itertools.product(['tt','ss','ff','fs','sf'],[0,25,40],[290,300,310],[.4,.5,.6],[20,250],[0,-140,140]))
        self.assertEqual(actual,expected)
        self.assertEqual(len(specs),810)

    def test_duty_changes_only_plateaus_and_title(self):
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            for s in target.specifications():
                old=target.source.fixture(Path('/out'),s);new=target.fixture(Path('/out'),s)
                for label,duty in [('VP0',s['duty']),('VP1',1-s['duty'])]:
                    words=re.search(r'^'+label+r'.*PULSE\(([^)]+)\)',new,re.M)[1].split()
                    ramp=float(words[3][:-1]);plateau=float(words[5][:-1]);period=float(words[6][:-1])
                    self.assertAlmostEqual((ramp+plateau)/period,duty)
                strip=lambda text:re.sub(r'^(VP[01].*PULSE\([^\n]+)\n','',text,flags=re.M).split('\n',1)[1]
                self.assertEqual(strip(old),strip(new))
                self.assertIn('VDD VDD 0 1.8\n',new)
                self.assertIn('.tran 1p '+str(2+1000/s['mhz']*18)+'n 0 1p',new)

    def test_transitive_models_cannot_be_omitted_or_changed(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);a=root/'a';b=root/'b'
            a.write_text('.lib tt\n.include "b"\n.endl tt\n');b.write_text('* primitive\n')
            known={str(p):target.sha(p) for p in [a,b]}
            self.assertEqual(target.model_closure(a,known),known)
            with self.assertRaises(ValueError):target.model_closure(a,{str(a):known[str(a)]})
            b.write_text('* changed\n')
            with self.assertRaises(ValueError):target.model_closure(a,known)

    def test_event_and_zero_phase_symmetry_required(self):
        result=dict(event_integrity_passed=True,pulse_generator_integrity_passed=True,symmetric_timing_passed=False)
        self.assertFalse(target.passed(result,dict(phase_error_ps=0)))
        self.assertTrue(target.passed(result,dict(phase_error_ps=140)))
        result['pulse_generator_integrity_passed']=False
        self.assertFalse(target.passed(result,dict(phase_error_ps=140)))


if __name__=='__main__':unittest.main()
