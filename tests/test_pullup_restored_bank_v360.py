# SPDX-License-Identifier: GPL-3.0-only
"""Guard the verified full-bank intervention and every original timing gate."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_pullup_restored_bank_v360 as p


class PullupRestoredBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=p.ROOT/'build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
        cls.local=p.ROOT/'build/diagnostics/restored_fine_recovery_v355/b88568e79d9ee803'
        cls.previous=json.loads((cls.parent/'manifest.json').read_text())['identity']
        cls.original=(cls.parent/'bank.spice').read_text()
        cls.wrapper=p.source.definition((cls.local/'pullup/bank.spice').read_text(),p.FINE)
        cls.text,cls.obs=p.transform(cls.original,cls.previous['observations'],cls.wrapper)

    def test_all_2126_native_devices_139_mim_and_every_original_control(self):
        _,leaves=p.source.inventory.native_leaves(p.source.collapse(self.text),p.TOP)
        self.assertEqual(sum('fet_' in d['model'] for d in leaves),2126)
        self.assertEqual(sum('cap_mim' in d['model'] for d in leaves),139)
        self.assertEqual(self.obs['controls'],self.previous['observations']['controls'])
        self.assertEqual(self.obs['programming_gates'],self.previous['observations']['programming_gates'])
        self.assertEqual(len(self.obs['controls']),86);self.assertEqual(len(self.obs['programming_gates']),266)
        actual={d['name']:d for d in self.obs['devices']}
        for gate in self.obs['programming_gates']:
            self.assertEqual(actual[gate['device']]['terminals'][1],gate['gate_node'])
        self.assertTrue(all(d['limit_v']==1.95 for d in self.obs['devices']))

    def test_only_verified_fine_call_changes_and_full_upstream_loading_remains(self):
        old=p.source.native.definitions(self.original);new=p.source.native.definitions(self.text)
        expected=[w[:-1]+[p.FINE] if w[0]=='Xfine_isolate' else w for w in old[p.source.TOP][1]]
        self.assertEqual(new[p.TOP][1],expected)
        self.assertEqual(p.source.definition(self.text,p.FINE),self.wrapper)
        for name in old:
            if name!=p.source.TOP:self.assertEqual(p.source.definition(self.text,name),p.source.definition(self.original,name))
        self.assertIn(['Xfine_pre','selected','pre_out','VGND','VPWR',p.source.SMALL],new[p.TOP][1])
        self.assertEqual(sum(d['name'].startswith('XD:Xfine_isolate:') for d in self.obs['devices']),112)
        before={d['name']:d for d in self.previous['observations']['devices']}
        after={d['name']:d for d in self.obs['devices']}
        self.assertTrue(all(after[n]==d for n,d in before.items() if not n.startswith('XD:Xfine_isolate:')))

    def test_incorrect_driver_wrapper_or_missing_programming_gate_is_rejected(self):
        wrong=self.wrapper.replace(p.recovery.PULLUP,p.source.REGULAR)
        with self.assertRaises(ValueError):p.transform(self.original,self.previous['observations'],wrong)
        old=deepcopy(self.previous['observations']);old['programming_gates'].pop()
        with self.assertRaises(ValueError):p.transform(self.original,old,self.wrapper)
        wrong=self.original.replace('Xfine_isolate pre_out fine_node','Xfine_isolate WRONG fine_node',1)
        with self.assertRaises(ValueError):p.transform(wrong,self.previous['observations'],self.wrapper)

    def test_full_original_zero_duty_coarse_eight_event_fixtures_are_retained(self):
        identity=dict(self.previous,observations=self.obs,**p.library_descriptor(self.previous))
        self.assertEqual([(s['coarse'],s['fine'],s['duty']) for s in p.specifications()],
                         [(0,0,.5),(0,31,.6),(0,31,.4),(1,0,.5)])
        for spec in p.specifications():
            text=p.fixture(p.ROOT/'build/unused-pullup-restored-bank',identity,spec)
            self.assertIn('.tran 2p 25n 0 2p',text)
            self.assertIn('VDD VDD 0 1.8',text)
            self.assertIn('CLOAD OUT 0 20f',text)
            self.assertEqual(text.count('tanh((time-'),16)
            self.assertEqual(text.count(p.TOP),1)
            self.assertIn('V(XD:pre_out)',text)
            self.assertNotIn('REPLAY',text)

    def test_real_preparation_descriptor_keeps_pdk_path_separate_from_macro_name(self):
        descriptor=p.library_descriptor(self.previous)
        self.assertEqual(descriptor['model'],self.previous['model'])
        self.assertEqual(descriptor['macro_top'],p.TOP)
        identity=dict(self.previous,observations=self.obs,**descriptor)
        text=p.fixture(p.ROOT/'build/unused-pullup-restored-bank',identity,p.specifications()[0])
        original=(self.parent/'0/bench.cir').read_text()
        self.assertEqual([line for line in text.splitlines() if line.startswith('.lib ')],
                         [line for line in original.splitlines() if line.startswith('.lib ')])
        bad=dict(self.previous,model=p.TOP)
        with self.assertRaises(ValueError):p.library_descriptor(bad)
        with self.assertRaises(ValueError):p.fixture(p.ROOT/'build/unused-pullup-restored-bank',
            dict(identity,model=p.TOP),p.specifications()[0])

    def test_any_individual_gate_or_either_overlap_can_reject_aggregate(self):
        # Synthetic timing arrays exercise the aggregation policy only.
        # They are not a native result or evidence for the new circuit.
        result=json.loads((self.local/'1/summary.json').read_text())['result'];rows=[]
        for k,spec in enumerate(p.specifications()):
            delay=100. if k==0 else 150. if k==3 else 200.
            r=dict(result,edge_delays_ps={e:[delay]*8 for e in ('rise','fall')})
            rows.append(dict(spec=spec,result=r,error=None))
        self.assertTrue(p.compare(rows)['component_hypothesis_passed'])
        self.assertFalse(p.compare(rows)['qualified_phy'])
        self.assertIsNone(p.compare(rows[:-1]))
        for key in ('all_input_output_pulses_present','zero_code_quarter_passed','terminal_screen_passed',
                    'period_screen_passed','repeated_delay_screen_passed','control_settling_passed'):
            changed=deepcopy(rows);changed[0]['result'][key]=False
            self.assertFalse(p.compare(changed)['component_hypothesis_passed'],key)
        changed=deepcopy(rows);changed[3]['result']['edge_delays_ps']['fall']=[250.]*8
        self.assertFalse(p.compare(changed)['component_hypothesis_passed'])
        changed=deepcopy(rows);changed[1]['result']['edge_delays_ps']['rise'].pop()
        self.assertFalse(p.compare(changed)['component_hypothesis_passed'])


if __name__=='__main__':unittest.main()
