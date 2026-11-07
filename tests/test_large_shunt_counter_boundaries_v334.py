# SPDX-License-Identifier: GPL-3.0-only
"""Keep the unchanged shunt screen complete and reuse its proven native point."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_large_shunt_counter_boundaries_v334 as probe

PARENT=ROOT/'build/diagnostics/request_taper_output_shunt_v332/89b05543a6a2dce0'


class LargeShuntBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=json.loads((PARENT/'manifest.json').read_text())['identity']
        cls.devices=cls.identity['devices'][probe.source.candidate.VARIANT]
        cls.result=json.loads((PARENT/'0/summary.json').read_text())['result']
        cls.tasks=probe.task_plan(PARENT,PARENT/'0',cls.devices)

    def test_exact_original_temperature_duty_and_stopped_level_axes(self):
        specs=probe.specifications()
        self.assertEqual(len(specs),12)
        self.assertEqual({(s['temperature'],s['duty'],s['stop_level']) for s in specs},
                         {(t,d,level) for t in (0,40) for d in (.4,.5,.6) for level in (0,1)})
        self.assertTrue(all(s['process']=='ss' and s['mhz']==410 and s['input_slew_ps']==100 for s in specs))
        self.assertEqual(specs[0],probe.source.specification())

    def test_only_eleven_new_native_runs_and_one_retained_case(self):
        self.assertEqual([t['mode'] for t in self.tasks],['retained']+['simulate']*11)
        self.assertEqual(self.tasks[0]['source_case'],str((PARENT/'0').relative_to(ROOT)))
        self.assertEqual(self.tasks[0]['deck_sha256'],probe.sha(PARENT/'0/bench.cir'))
        self.assertEqual([t['id'] for t in self.tasks],list(map(str,range(12))))

    def test_full_native_stimulus_and_observations_unchanged(self):
        old=(PARENT/'0/bench.cir').read_text().splitlines()
        new=probe.fixture(PARENT,probe.specifications()[0],self.devices).splitlines()
        self.assertEqual(old[1:],new[1:])
        self.assertNotEqual(old[0],new[0])
        original_print=next(v for v in old if v.startswith('.print '))
        for spec in probe.specifications():
            lines=probe.fixture(PARENT,spec,self.devices).splitlines()
            self.assertIn('.tran 1p 26n 0 1p',lines)
            self.assertEqual(next(v for v in lines if v.startswith('.print ')),original_print)
            self.assertEqual(next(v for v in lines if v.startswith('VDD ')),next(v for v in old if v.startswith('VDD ')))

    def test_incomplete_coverage_or_failed_native_gate_cannot_pass(self):
        rows=[dict(task=t,result=copy.deepcopy(self.result),error=None) for t in self.tasks]
        self.assertTrue(probe.assess(rows)['component_hypothesis_passed'])
        self.assertIsNone(probe.assess(rows[:-1]))
        with self.assertRaisesRegex(ValueError,'exact original duty'):probe.assess(list(reversed(rows)))
        rows[9]['result']['terminal_screen_passed']=False
        self.assertFalse(probe.assess(rows)['component_hypothesis_passed'])
        rows[10]['result']=None
        self.assertIsNone(probe.assess(rows))

    def test_all_native_stress_entries_and_positive_low_windows_required(self):
        self.assertTrue(probe.point_passed(self.result))
        bad=copy.deepcopy(self.result);bad['terminal_stress'][0]['max_terminal_difference_v']=1.96
        self.assertFalse(probe.point_passed(bad))
        bad=copy.deepcopy(self.result);bad['terminal_stress'].pop()
        self.assertFalse(probe.point_passed(bad))
        bad=copy.deepcopy(self.result);bad['low_windows']['minimum_remaining_low_window_ps']=0
        self.assertFalse(probe.point_passed(bad))


if __name__=='__main__':unittest.main()
