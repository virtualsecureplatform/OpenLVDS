# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from qualify_receiver_components import cases,rebind,static_metrics,check_coverage
ROOT=Path(__file__).resolve().parents[1]


class ReceiverComponentQualification(unittest.TestCase):
    def test_full_coverage_has_sixty_distinct_conditions(self):
        req=json.loads((ROOT/'requirements.json').read_text());all_cases=cases(req)
        self.assertEqual(len(all_cases),60);self.assertEqual(len(set(all_cases)),60)
        for view in ['schematic','native']:
            for test in ['receiver','receiver_rate']:
                self.assertEqual({(p,t) for v,k,p,t in all_cases if (v,k)==(view,test)},
                                 {(p,t) for p in req['process_corners'] for t in [0,25,40]})

    def test_fixture_changes_only_library_binding(self):
        deck='Title\n.include "/old/source.spice"\nVD VDDD 0 1.8\nCQ Q 0 100f\n.tran 10p 144n 0 50p\n.end\n'
        result=rebind(deck,Path('/old'),Path('/new'))
        self.assertEqual(result.replace('/new/source.spice','/old/source.spice'),deck)
        with self.assertRaisesRegex(ValueError,'one captured'):rebind(deck+deck,Path('/old'),Path('/new'))

    def test_missing_duplicate_or_mislabeled_cases_fail_before_simulation(self):
        req=json.loads((ROOT/'requirements.json').read_text())
        tasks=[dict(id=f'{v}_{k}_{p}_{t}',view=v,test=k,process=p,temperature=t) for v,k,p,t in cases(req)]
        check_coverage(tasks,req)
        for bad in [tasks[:-1],tasks[:-1]+[tasks[0]]]:
            with self.assertRaisesRegex(ValueError,'coverage'):check_coverage(bad,req)
        tasks[0]=dict(tasks[0],id='another_case')
        with self.assertRaisesRegex(ValueError,'case name'):check_coverage(tasks,req)

    def waveform(self):
        t=np.linspace(0,144e-9,14401);wave=np.zeros((len(t),5));wave[:,1]=t
        wave[:,4]=(np.floor(t/12e-9).astype(int)%2)*1.8
        return wave

    def test_every_static_common_mode_and_polarity_must_pass(self):
        wave=self.waveform();result=static_metrics(wave)
        self.assertTrue(result['passed']);self.assertEqual(len(result['points']),12)
        at=np.argmin(abs(wave[:,1]-58e-9));wave[at-1:at+2,4]=.8
        result=static_metrics(wave)
        self.assertFalse(result['passed']);self.assertFalse(result['points'][4]['passed'])

    def test_static_interpolation_cannot_hide_a_truncated_trace(self):
        wave=self.waveform()
        with self.assertRaisesRegex(ValueError,'Incomplete'):static_metrics(wave[wave[:,1]<80e-9])
