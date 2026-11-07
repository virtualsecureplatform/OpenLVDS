# SPDX-License-Identifier: GPL-3.0-only
"""Check actual shunt placement, native contacts and preserved buffer escapes."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    import build_shunted_counter_v344 as p
except ModuleNotFoundError as error:
    if error.name not in ('klayout','numpy'):
        raise
    p=None


@unittest.skipIf(p is None,'requires project counter-physical Python with NumPy and KLayout')
class ShuntedCounterPhysicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=json.loads((p.material.PLAN/'manifest.json').read_text())['identity']
        folder=ROOT/'build/diagnostics/counter_output_mim5_physical_v336/80531cf7f88fa1a5'
        r=json.loads((folder/'summary.json').read_text())
        row=dict(r['physical'],ports=r['plan']['ports'],macro=p.material.CAP,
            gds_sha256=p.sha(folder/(p.material.CAP+'.gds')),lef_sha256=p.sha(folder/(p.material.CAP+'.lef')))
        cls.macros=deepcopy(cls.old['macros'])
        cls.macros[p.material.CAP]=p.assembly.macro(p.material.CAP,folder,row)
        cls.cells=p.material.add_shunt(cls.old['cells'])
        cls.plan=p.route_plan(cls.old,cls.cells,cls.macros)

    def test_actual_shunt_preserves_old_placement_and_separated_buffer_routes(self):
        self.assertEqual({k:v for k,v in self.plan['placements'].items() if k!=p.material.ROLE},
                         self.old['plan']['placements'])
        self.assertEqual(self.plan['placements'][p.material.ROLE],dict(x=85.,y=14.38))
        self.assertEqual(self.plan['shunt_connection'],dict(Y='low0_sn',VGND='VGND'))
        self.assertEqual(self.plan['base_escapes'],p.escape.routes(self.old))
        self.assertEqual(p.contact.contacts(self.plan['all_m4_m5_shapes']),[])
        self.assertEqual(p.material.planning.overlaps(self.cells,self.macros,self.plan['placements']),[])
        self.assertEqual(self.plan['ground_setter_contact'],dict(x_um=83.5,y_um=14.2))

    def test_actual_additions_avoid_foreign_native_masks_including_cap_bottom_landing(self):
        proof=p.check_native_contacts(self.cells,self.macros,self.plan)
        self.assertEqual(proof['foreign_native_m4_m5_contacts'],0)
        self.assertGreater(proof['native_layer_contact_checks'],704)
        witness=p.native_witness(self.macros)
        self.assertTrue(witness['all_native_masks_and_electrical_labels_preserved'])
        self.assertEqual(witness['text_height_difference_masters'],['sky130_fd_sc_hd__tapvpwrvgnd_1'])

    def test_bottom_connection_on_top_electrode_is_rejected(self):
        plan=deepcopy(self.plan)
        a=self.plan['placements'][p.material.ROLE]
        pin=self.macros[p.material.CAP]['row']['ports']['Y']
        xy=(a['x']+pin['x_um'],a['y']+pin['y_um'])
        plan['shunt_shapes'].append(dict(net='VGND',layer='metal4',rect=p.escape.rect(xy,xy,.4),
            kind='injected_bottom_on_top',cell=p.material.ROLE))
        with self.assertRaisesRegex(ValueError,'foreign native metal4'):
            p.check_native_contacts(self.cells,self.macros,plan)

    def test_changed_electrodes_and_unaligned_accesses_are_rejected(self):
        cells=deepcopy(self.cells);cells[-1]['pins']['Y']='low0'
        with self.assertRaisesRegex(ValueError,'exact passed 23-role'):
            p.route_plan(self.old,cells,self.macros)
        macros=deepcopy(self.macros)
        macros[p.material.CAP]['row']['ports']['VGND']['y_um']+=.1
        with self.assertRaisesRegex(ValueError,'aligned native capacitor'):
            p.route_plan(self.old,self.cells,macros)

    def test_text_policy_ignores_only_height_and_retains_names_positions_and_layers(self):
        def labels(name='VGND',x=100,layer=68,height=125):
            lib=p.db.Layout();cell=lib.create_cell('tap')
            text=p.db.Text(name,p.db.Trans(x,5));text.size=height
            cell.shapes(lib.layer(layer,5)).insert(text)
            return p.electrical_texts(lib,cell)
        self.assertEqual(labels(),labels(height=156))
        self.assertNotEqual(labels(),labels(name='VPWR'))
        self.assertNotEqual(labels(),labels(x=101))
        self.assertNotEqual(labels(),labels(layer=71))


if __name__=='__main__':unittest.main()
