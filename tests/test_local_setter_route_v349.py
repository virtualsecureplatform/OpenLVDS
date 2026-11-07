# SPDX-License-Identifier: GPL-3.0-only
"""Guard the local mixed-layer first-setter repair without changing native logic."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
try:
    import build_shunted_counter_v349 as p
except ModuleNotFoundError as error:
    if error.name not in ('klayout','numpy'):raise
    p=None


@unittest.skipIf(p is None,'requires project counter-physical Python with NumPy and KLayout')
class LocalSetterRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=json.loads((p.material.PLAN/'manifest.json').read_text())['identity']
        cls.previous=json.loads((ROOT/'build/diagnostics/shunted_counter_physical_v345/7ac98cd80b7cddbe/manifest.json').read_text())['identity']
        cls.cells=cls.previous['cells'];cls.macros=cls.previous['macros']
        cls.plan=p.route_plan(cls.old,cls.cells,cls.macros)

    def test_only_first_setter_bus_is_replaced_and_native_placement_is_retained(self):
        self.assertEqual(self.plan['placements'],self.previous['plan']['placements'])
        self.assertEqual(self.plan['points'],{n:e for n,e in self.previous['plan']['points'].items() if n!='low0_sn'})
        self.assertEqual(self.plan['buses'],{n:y for n,y in self.previous['plan']['buses'].items() if n!='low0_sn'})
        self.assertEqual(self.plan['direct_feedback'][:-1],self.previous['plan']['direct_feedback'])
        wire=self.plan['direct_feedback'][-1]
        self.assertEqual(wire['net'],'low0_sn')
        self.assertEqual([(e['cell'],e['pin'],e['layer']) for e in wire['ends']],
            [(p.material.ROLE,'Y','metal4'),('low0_q','A','metal3')])
        self.assertEqual(self.plan['shunt_shapes'],self.previous['plan']['shunt_shapes'])

    def test_local_route_avoids_native_masks_and_no_via3_is_added_to_top_electrode(self):
        self.assertEqual(p.check_native_contacts(self.cells,self.macros,self.plan)
            ['foreign_native_m3_m4_m5_contacts'],0)
        landings=[s for s in p.m3_shapes(self.cells,self.macros,self.plan) if s['net']=='low0_sn']
        self.assertEqual(len(landings),1)
        end=self.plan['direct_feedback'][-1]['ends'][1]
        self.assertEqual(landings[0]['rect'],p.escape.rect((end['x_um'],end['y_um']),
            (end['x_um'],end['y_um']),.4))

    def test_first_setter_signal_parent_metal_area_is_reduced(self):
        def area(plan):
            total=0
            for layer in ('metal4','metal5'):
                region=p.db.Region()
                for row in plan['all_m4_m5_shapes']:
                    if row['net']=='low0_sn' and row['layer']==layer:
                        region.insert(p.db.Box(*[round(v*1000) for v in row['rect']]))
                total+=region.merged().area()
            return total
        self.assertLess(area(self.plan),.5*area(self.previous['plan']))
        # This is an area check; extracted capacitance and native timing must
        # still be measured with the changed metal and original 5x5 capacitor.

    def test_actual_isolated_failure_evidence_is_bound_before_geometry(self):
        expected,paths,cause=p.timing_evidence()
        self.assertLess(cause['minimum_remaining_low_window_ps'],0)
        self.assertEqual(cause['case'],str(p.TIMING_CASE.relative_to(ROOT)))
        self.assertIn(p.TIMING_PROOF,paths)
        self.assertFalse(any(n.endswith('.raw') for n in expected))


if __name__=='__main__':unittest.main()
