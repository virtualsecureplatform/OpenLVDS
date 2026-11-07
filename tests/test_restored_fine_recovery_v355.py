# SPDX-License-Identifier: GPL-3.0-only
"""Guard native recovery isolation, exact intervention and baseline parity gates."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_restored_fine_recovery_v355 as p


class RestoredFineRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=p.ROOT/'build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
        cls.manifest=json.loads((cls.parent/'manifest.json').read_text())
        cls.previous=cls.manifest['identity']['observations']
        cls.original=(cls.parent/'bank.spice').read_text()
        cls.variants={v:p.transform(cls.original,cls.previous,v) for v in p.VARIANTS}

    def test_exact_native_inventory_all_controls_and_doubled_programming_gates(self):
        for variant,(text,obs) in self.variants.items():
            self.assertEqual(len(obs['devices']),p.COUNTS[variant])
            self.assertEqual(len(obs['controls']),62);self.assertEqual(len(obs['programming_gates']),186)
            devices={d['name']:d for d in obs['devices']}
            for gate in obs['programming_gates']:
                self.assertEqual(gate['gate_node'],devices[gate['device']]['terminals'][1])
            _,leaves=p.source.inventory.native_leaves(p.source.collapse(text),p.TOP)
            self.assertEqual(sum('fet_' in d['model'] for d in leaves),p.COUNTS[variant])
            self.assertEqual(sum('cap_mim' in d['model'] for d in leaves),66)

    def test_only_loaded_driver_changes_and_pre_final_native_loading_remains(self):
        old=p.source.native.definitions(self.original)
        wanted={f'Xfine_{kind}{k}' for kind in ('buffer','inverse','unit','copy') for k in range(31)}
        wanted.update(('Xfine_pre','Xfine_isolate','Xfine_regenerate1'))
        kept=[w for w in old[p.source.TOP][1] if w[0] in wanted]
        for variant,(text,_) in self.variants.items():
            defs=p.source.native.definitions(text)
            actual=defs[p.TOP][1]
            expected=[w[:-1]+[p.STRONG] if variant=='pullup' and w[0]=='Xfine_isolate' else w for w in kept]
            self.assertEqual(actual,expected+[['Rboundary','selected','REPLAY','1m']])
            for name in old:
                if name!=p.source.TOP:self.assertEqual(p.source.definition(text,name),p.source.definition(self.original,name))
        strong=p.source.native.definitions(self.variants['pullup'][0])[p.STRONG]
        self.assertEqual(strong,(['A','Y','VGND','VPWR'],[['Xa','A','Y','VGND','VPWR',p.PULLUP],
                                                         ['Xb','A','Y','VGND','VPWR',p.PULLUP]]))

    def test_reject_missing_fine_copy_shared_passive_or_wrong_path(self):
        body=p.source.native.definitions(self.original)[p.source.TOP][1]
        call=next(w for w in body if w[0]=='Xfine_copy0')
        missing=self.original.replace(' '.join(call)+'\n','',1)
        with self.assertRaises(ValueError):p.transform(missing,self.previous,'baseline')
        passive=self.original.replace('.subckt '+p.source.TOP+' ','.subckt '+p.source.TOP+' ',1)
        passive=passive.replace('.ends '+p.source.TOP,'Runexpected selected 0 1k\n.ends '+p.source.TOP,1)
        with self.assertRaises(ValueError):p.transform(passive,self.previous,'baseline')
        wrong=self.original.replace('Xfine_pre selected pre_out','Xfine_pre selected WRONG',1)
        with self.assertRaises(ValueError):p.transform(wrong,self.previous,'baseline')

    def test_original_full_stimulus_solver_and_native_terminal_saving(self):
        identity=dict(original_fixture=(self.parent/'1/bench.cir').read_text(),
                      observations={v:obs for v,(_,obs) in self.variants.items()})
        for variant in p.VARIANTS:
            deck=p.fixture(p.ROOT/'build/unused-restored-recovery',identity,variant)
            self.assertIn('.tran 2p 25n 0 2p',deck)
            self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',deck)
            self.assertIn('VDD VDD 0 1.8',deck)
            self.assertIn('V(XD:pre_out)',deck)
            self.assertIn('V(XD:fine_node)',deck)
            self.assertEqual(deck.count('tanh((time-'),16)
            self.assertNotIn('.ic ',deck)

    def test_all_sample_recorded_source_keeps_zero_and_full_stop(self):
        times=np.array([0.,1e-15,2e-9,25e-9]);values=np.array([1.8,1.80001,1.79,1.8])
        wave=p.recorded.waveform(times,values)
        self.assertEqual(wave.count('\n'),6)
        pairs=[tuple(map(float,line.split()[1:])) for line in wave.splitlines()[1:-1]]
        np.testing.assert_array_equal(np.array(pairs),np.column_stack([times,values]))
        with self.assertRaises(ValueError):p.recorded.waveform(times[1:],values[1:])

    def test_failed_parity_or_safety_blocks_intervention_without_waiving_history(self):
        result=dict(baseline_parity=dict(parity_passed=True),
            **{k:True for k in ('all_input_output_pulses_present','input_timing_stimulus_passed',
            'full_swing_pulses_passed','unwrapped_native_epoch_passed','pulse_order_and_widths_passed',
            'terminal_screen_passed','control_settling_passed')})
        result.update(period_screen_passed=False,repeated_delay_screen_passed=False,qualified_phy=False)
        self.assertTrue(p.recorded.baseline_usable(result))
        for key in ('terminal_screen_passed','control_settling_passed'):
            changed=deepcopy(result);changed[key]=False
            self.assertFalse(p.recorded.baseline_usable(changed))
        changed=deepcopy(result);changed['baseline_parity']['parity_passed']=False
        self.assertFalse(p.recorded.baseline_usable(changed))
        self.assertFalse(p.recorded.baseline_usable(None))
        self.assertFalse(result['qualified_phy'])


if __name__=='__main__':unittest.main()
