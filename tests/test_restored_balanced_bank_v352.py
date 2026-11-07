# SPDX-License-Identifier: GPL-3.0-only
"""Guard complete restored-bank topology, typed controls and original timing gates."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_restored_balanced_bank_v352 as p


class RestoredBalancedBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous=json.loads((p.PARENT/'manifest.json').read_text())['identity']
        cls.original=(p.PARENT/'bank.spice').read_text()
        report=json.loads((p.DRIVERS/'summary.json').read_text())
        row=next(r for r in report['rows'] if r['macro']==p.SMALL)
        cls.small=p.definition((p.ROOT/row['extraction']['netlist']).read_text(),p.SMALL)
        cls.text,cls.observations,cls.revision=p.transform(cls.original,cls.previous['observations'],cls.small)

    def test_exact_complete_native_inventory_and_every_programming_gate(self):
        _,devices=p.inventory.native_leaves(p.collapse(self.text),p.TOP)
        self.assertEqual(sum('fet_' in d['model'] for d in devices),2086)
        self.assertEqual(sum('cap_mim' in d['model'] for d in devices),139)
        self.assertEqual(self.observations['controls'],self.previous['observations']['controls'])
        self.assertEqual(len(self.observations['programming_gates']),266)
        self.assertEqual(self.observations['programming_gates'][:173],self.previous['observations']['programming_gates'])
        mapped={d['name']:d for d in self.observations['devices']}
        for gate in self.observations['programming_gates']:
            self.assertEqual(mapped[gate['device']]['terminals'][1],gate['gate_node'])
        self.assertTrue(all(d['limit_v']==1.95 for d in mapped.values()))

    def test_four_inversion_path_and_balanced_native_units_are_explicit(self):
        definitions=p.native.definitions(self.text);body=definitions[p.TOP][1]
        self.assertIn(['Xfine_pre','selected','pre_out','VGND','VPWR',p.SMALL],body)
        self.assertIn(['Xfine_isolate','pre_out','fine_node','VGND','VPWR',p.FINE],body)
        self.assertIn(['Xfine_regenerate1','fine_node','OUT','VGND','VPWR',p.REGULAR],body)
        self.assertEqual(definitions[p.COARSE][1],[['Xa','IN','mid','VPWR','VGND',p.GROUP],
                                                 ['Xb','mid','OUT','VPWR','VGND',p.GROUP]])
        self.assertEqual(definitions[p.FINE][1],[['Xa','A','Y','VGND','VPWR',p.REGULAR],
                                               ['Xb','A','Y','VGND','VPWR',p.REGULAR]])
        self.assertEqual(self.revision['path_inversions'],4)
        self.assertEqual(self.revision['input_to_output_polarity'],'noninverting')
        for k in range(4):
            self.assertIn([f'Xgroup_compound{k}',f'tree0_{k}',f'regenerated{k}','VPWR','VGND',p.GROUP],body)
        for model,input_pin in ((p.GROUP,'IN'),(p.SMALL,'A'),(p.REGULAR,'A')):
            _,leaves=p.inventory.native_leaves(p.collapse(self.text),model)
            self.assertEqual({d['nodes'][1] for d in leaves if 'fet_' in d['model']},{input_pin})

    def test_existing_components_and_all_full_fixture_events_are_retained(self):
        for name in p.native.definitions(self.original):
            if name!=p.baseline.TOP:self.assertEqual(p.definition(self.text,name),p.definition(self.original,name))
        identity=dict(self.previous,observations=self.observations)
        text=p.fixture(p.ROOT/'build/unused-restored-bank-test',identity,p.specifications()[0])
        self.assertIn('.tran 2p 25n 0 2p',text)
        self.assertIn('VDD VDD 0 1.8',text)
        self.assertIn('V(XD:pre_out)',text)
        self.assertNotIn('V(XD:restored_b)',text)
        self.assertEqual(text.count(p.TOP),1)
        self.assertTrue(all(s['cycles']==8 and s['stop_ns']==25 and s['load_ff']==20 for s in p.specifications()))
        self.assertEqual([(s['coarse'],s['fine'],s['duty']) for s in p.specifications()],
                         [(0,0,.5),(0,31,.6),(0,31,.4),(1,0,.5)])

    def test_unexpected_gate_inventory_or_fine_wiring_is_rejected(self):
        previous=deepcopy(self.previous['observations']);previous['programming_gates'].pop()
        with self.assertRaises(ValueError):p.transform(self.original,previous,self.small)
        wrong=self.original.replace('Xfine_unit0 fine_node ','Xfine_unit0 WRONG_NODE ',1)
        with self.assertRaises(ValueError):p.transform(wrong,self.previous['observations'],self.small)

    def test_original_zero_and_range_failures_cannot_pass_aggregate(self):
        rows=[json.loads((p.PARENT/str(k)/'summary.json').read_text()) for k in range(4)]
        rows=[dict(row,spec=p.specifications()[k]) for k,row in enumerate(rows)]
        self.assertFalse(p.compare(rows)['component_hypothesis_passed'])
        self.assertLess(p.compare(rows)['conservative_coarse_overlap_ps']['rise'],0)
        self.assertLess(p.compare(rows)['conservative_coarse_overlap_ps']['fall'],0)
        # Even hypothetical positive overlap cannot excuse a failed individual
        # quarter, voltage, control, slew or period/history gate.
        rows=deepcopy(rows)
        for row in rows[1:3]:
            row['result']['edge_delays_ps']={edge:[1200.]*8 for edge in ('rise','fall')}
        self.assertFalse(p.compare(rows)['component_hypothesis_passed'])
        rows[0]['result']['current_clock_interface_screen_passed']=True
        self.assertFalse(p.compare(rows)['component_hypothesis_passed'])
        rows[0]['result']['zero_code_quarter_passed']=True
        rows[0]['result']['periodic_transport_screen_passed']=True
        self.assertTrue(p.compare(rows)['component_hypothesis_passed'])
        rows[2]['result']['edge_delays_ps']['fall'].pop()
        self.assertFalse(p.compare(rows)['component_hypothesis_passed'])


if __name__=='__main__':unittest.main()
