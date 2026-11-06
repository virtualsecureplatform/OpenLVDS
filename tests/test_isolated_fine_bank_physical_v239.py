# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolated_fine_bank_physical_v239 as design
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/diagnostics/balanced_placement_v129/a158104d2fd54d99'
VIEWS=ROOT/'build/diagnostics/isolated_fine_cell_views_v236/b040d127238a22fa'
PILOT=ROOT/'build/diagnostics/discharge_isolated_fine_bank_v220/9e4d0f5b90541807/p20n16_c1/bank.spice'

@unittest.skipUnless((BASE/'manifest.json').exists() and (VIEWS/'summary.json').exists() and PILOT.exists(),'Native bank evidence required')
class IsolatedBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((BASE/'manifest.json').read_text())['identity']
        cls.records={**cls.before['records'],**json.loads((VIEWS/'summary.json').read_text())['cells']}
        cls.graph=design.graph(cls.before['graph']);cls.component=PILOT.read_text()

    def test_only_fine_signal_path_changes(self):
        old={c['name']:c for c in self.before['graph']['cells']}
        new={c['name']:c for c in self.graph['cells']}
        self.assertEqual(set(old)-set(new),{'u_fine_compound'})
        self.assertEqual(set(new)-set(old),{'u_fine_isolate','u_fine_regenerate'})
        for name,c in old.items():
            if name=='u_fine_compound':continue
            expected=deepcopy(c)
            if name.startswith('u_fine_unit'):expected['pins']['A']='fine_node'
            self.assertEqual(new[name],expected)
        self.assertTrue(design.compare_component(self.graph,self.component)['exact_component_calls_and_named_pins_verified'])

    def test_wrong_programming_gate_is_rejected(self):
        g=deepcopy(self.graph)
        next(c for c in g['cells'] if c['name']=='u_fine_unit0')['pins']['CTRL']='fine1'
        with self.assertRaisesRegex(ValueError,'differs from native'):
            design.compare_component(g,self.component)
        before=deepcopy(self.before['graph'])
        next(c for c in before['cells'] if c['name']=='u_fine_unit0')['pins']['CTRL_B']='fine_b1'
        with self.assertRaisesRegex(ValueError,'programming connections'):
            design.graph(before)

    def test_complete_native_inventory_matches_the_component_experiment(self):
        reference=design.original.native_source(self.graph,[(BASE/'reference.spice').read_text(),
            *[(VIEWS/'native'/m/(m+'.sch.spice')).read_text() for m in (design.DRIVER,design.BUFFER)]])
        proof=design.inventory_proof(self.graph,reference,self.component)
        self.assertEqual((proof['native_mos'],proof['native_mims']),(1479,43))

    def test_shifted_fine_array_preserves_complete_tapped_rows(self):
        p=design.placement(self.before['plan'],self.graph,self.records)
        self.assertEqual(p['functional_instances'],180)
        self.assertEqual({r['net'] for r in p['fixed_routes']},{'fine_node','VPWR','VGND'})
        for name,xy in self.before['plan']['placements'].items():
            if name=='u_fine_compound':continue
            new=p['placements'][name]
            if new!=xy:
                self.assertEqual(new,[design.floor.q(xy[0]+49*design.floor.SITE),xy[1]])
        self.assertFalse(p['routed'])
        self.assertFalse(p['whole_bank_lvs_passed'])

if __name__=='__main__':unittest.main()
