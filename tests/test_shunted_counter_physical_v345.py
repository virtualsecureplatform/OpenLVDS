# SPDX-License-Identifier: GPL-3.0-only
"""Reproduce the retained native M3 short and check repaired full-layer routing."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    import build_shunted_counter_v345 as p
except ModuleNotFoundError as error:
    if error.name not in ('klayout','numpy'):raise
    p=None


@unittest.skipIf(p is None,'requires project counter-physical Python with NumPy and KLayout')
class RepairedShuntedCounterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.failed=json.loads((p.FAILED/'manifest.json').read_text())['identity']
        cls.old=json.loads((p.material.PLAN/'manifest.json').read_text())['identity']
        cls.cells=cls.failed['cells'];cls.macros=cls.failed['macros']
        cls.plan=p.route_plan(cls.old,cls.cells,cls.macros)

    def test_original_native_m3_short_is_reproduced_and_new_routes_are_clear(self):
        with self.assertRaisesRegex(ValueError,'foreign native metal3'):
            p.check_native_contacts(self.cells,self.macros,self.failed['plan'])
        proof=p.check_native_contacts(self.cells,self.macros,self.plan)
        self.assertEqual(proof['foreign_native_m3_m4_m5_contacts'],0)
        self.assertGreater(proof['native_layer_contact_checks'],10000)

    def test_only_parallel_buffers_move_and_supply_stems_follow(self):
        for role,pos in self.old['plan']['placements'].items():
            expected=dict(pos)
            if role in ('request_driver_parallel','clock_driver_parallel'):expected['x']+=40.
            self.assertEqual(self.plan['placements'][role],expected)
        for net in ('VGND','VPWR'):
            for old,new in zip(self.old['plan']['points'][net],self.plan['points'][net]):
                expected=dict(old)
                if old['cell'] in ('request_driver_parallel','clock_driver_parallel'):expected['x']+=40.
                self.assertEqual(new,expected)
        self.assertEqual(p.material.planning.overlaps(self.cells,self.macros,self.plan['placements']),[])
        self.assertEqual(self.plan['direct_feedback'],self.old['plan']['direct_feedback'])

    def test_actual_m5_union_has_no_subminimum_spacing_or_notches(self):
        def violations(plan):
            region=p.db.Region()
            for row in plan['all_m4_m5_shapes']:
                if row['layer']=='metal5':region.insert(p.db.Box(*[round(x*1000) for x in row['rect']]))
            return region.merged().space_check(1600)
        self.assertFalse(violations(self.failed['plan']).is_empty())
        self.assertTrue(violations(self.plan).is_empty())
        self.assertEqual(self.plan['buses']['RCLK'],234.)

    def test_restoring_old_parallel_supply_tracks_is_rejected(self):
        plan=deepcopy(self.plan)
        for net in ('VGND','VPWR'):
            for end in plan['points'][net]:
                if end['cell']=='clock_driver_parallel':end['x']-=40.
        with self.assertRaisesRegex(ValueError,'foreign native metal3'):
            p.check_native_contacts(self.cells,self.macros,plan)


if __name__=='__main__':unittest.main()
