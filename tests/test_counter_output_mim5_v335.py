# SPDX-License-Identifier: GPL-3.0-only
"""Tie physical capacitor material to the passed native source and exact masks."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    import build_counter_output_mim5_v335 as physical
except ModuleNotFoundError as error:
    if error.name!='klayout':raise
    physical=None


@unittest.skipIf(physical is None,'requires pinned CAD KLayout interpreter')
class CounterMimPhysicalTests(unittest.TestCase):
    def test_exact_two_terminal_native_five_micron_capacitor(self):
        ports,leaves=physical.inventory.native_leaves(physical.schematic(),physical.NAME)
        self.assertEqual(ports,['Y','VGND'])
        self.assertEqual(len(leaves),1)
        self.assertEqual(leaves[0]['model'],physical.CAP)
        self.assertEqual(leaves[0]['nodes'],['Y','VGND'])
        self.assertEqual({k:physical.inventory.exact_number(v) for k,v in leaves[0]['params'].items()},dict(w=5,l=5))

    def test_native_top_bottom_electrodes_and_positive_placement(self):
        info=dict(bbox=[-3.58,-2.7,3.58,2.7],ports=dict(C1=['mimcapcontact',-.88,0.],C2=['via3',3.32,0.]))
        plan=physical.access_plan(info)
        self.assertEqual((plan['dx_um'],plan['dy_um']),(3.58,2.7))
        self.assertEqual(plan['ports']['Y']['layer'],'metal4')
        self.assertEqual(plan['ports']['VGND']['layer'],'metal3')
        self.assertAlmostEqual(plan['ports']['Y']['x_um'],2.7)
        self.assertAlmostEqual(plan['ports']['VGND']['x_um'],6.9)
        wrong=copy.deepcopy(info);wrong['ports']['C1'][0]='via3'
        with self.assertRaisesRegex(ValueError,'native top/bottom'):physical.access_plan(wrong)

    def test_changed_mask_rejected_and_translation_preserved(self):
        db=physical.db
        a=db.Layout();a.dbu=.001;ca=a.create_cell('native');ca.shapes(a.layer(71,20)).insert(db.Box(0,0,1000,1000))
        b=db.Layout();b.dbu=.001;cb=b.create_cell('wrapper');layer=b.layer(71,20)
        cb.shapes(layer).insert(db.Box(1000,2000,2000,3000))
        self.assertTrue(physical.masks_equal(a,ca,b,cb,1,2)['all_native_masks_preserved'])
        cb.shapes(layer).insert(db.Box(3000,3000,3200,3200))
        with self.assertRaisesRegex(ValueError,'masks changed'):physical.masks_equal(a,ca,b,cb,1,2)

    def test_source_must_be_the_complete_passed_five_micron_circuit(self):
        parent=ROOT/'build/diagnostics/request_taper_output_shunt_v332/89b05543a6a2dce0'
        report=json.loads((ROOT/'build/reports/request_taper_large_shunt_native_replay/20261107T061754Z/summary.json').read_text())
        manifest=json.loads((parent/'manifest.json').read_text())
        row=json.loads((parent/'0/summary.json').read_text());state=json.loads((parent/'state.json').read_text())
        physical.validate_source(report,manifest,row,state)
        wrong=copy.deepcopy(manifest);wrong['identity']['added_native_mim']['width_um']=6
        with self.assertRaisesRegex(ValueError,'passing 5x5'):physical.validate_source(report,wrong,row,state)
        bad=copy.deepcopy(row);bad['result']['terminal_screen_passed']=False
        with self.assertRaisesRegex(ValueError,'passing 5x5'):physical.validate_source(report,manifest,bad,state)
        with self.assertRaisesRegex(ValueError,'passing 5x5'):physical.validate_source(report,manifest,row,dict(status='running',qualified_phy=False))


if __name__=='__main__':unittest.main()
