# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_fast_clear_counter_v267 as candidate


class FastClearCounterTests(unittest.TestCase):
    def original(self):
        path=candidate.ROOT/'build/diagnostics/strong_storage_counter_physical_v234/a3c3c8188cdb61a3/manifest.json'
        if not path.exists():self.skipTest('Native physical counter fixture unavailable')
        return json.loads(path.read_text())['identity']

    def test_only_two_high_phase_models_change_with_all_pin_maps_preserved(self):
        identity=self.original();before=deepcopy(identity['cells']);after=candidate.changed_cells(before)
        self.assertEqual(before,identity['cells']);self.assertEqual(len(after),22)
        for old,new in zip(before,after):
            if old['name'] in candidate.SETTERS:self.assertEqual(new,dict(old,model=candidate.NEW))
            else:self.assertEqual(new,old)
        bad=deepcopy(before);next(c for c in bad if c['name']=='high1_set')['model']='other'
        with self.assertRaisesRegex(ValueError,'setter models'):candidate.changed_cells(bad)
        with self.assertRaisesRegex(ValueError,'22-macro'):candidate.changed_cells(before[:-1])

    def test_actual_native_census_and_all_three_direct_feedback_routes_regenerate(self):
        identity=self.original();cells=candidate.changed_cells(identity['cells']);macros=identity['macros']
        self.assertEqual(candidate.census(cells,macros),dict(native_primitives=630,native_model_counts={
            'sky130_fd_pr__nfet_01v8':290,'sky130_fd_pr__pfet_01v8_hvt':290,'sky130_fd_pr__cap_mim_m3_1':50}))
        plan=candidate.source.strong_plan(cells,macros,candidate.source.original.default_plan())
        self.assertEqual(set(plan['placements']),{c['name'] for c in cells})
        self.assertEqual({r['net'] for r in plan['direct_feedback']},{'low0_qb','low1_qb','low2_qb'})
        self.assertEqual(len([c for c in cells if c['name'].startswith('request_driver')]),2)


if __name__=='__main__':unittest.main()
