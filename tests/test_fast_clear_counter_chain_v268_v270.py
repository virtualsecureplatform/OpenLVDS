# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_fast_clear_counter_rc_v268 as rc
import probe_fast_clear_counter_shared_rc_v269 as transient
import probe_strong_storage_counter_shared_rc_v232 as original
import run_fast_clear_counter_followup_v270 as follow


class FastClearChainTests(unittest.TestCase):
    def physical(self):
        return dict(fast_clear_counter_physical_passed=True,same_phase_logic=True,
            high_phase_setters_strengthened=['high1_set','high2_set'],physical=dict(passed=True,drc_count='0',lvs_passed=True,macro_count=22,
                native_master_witness={k:True for k in ('all_shared_native_masters_identical','all_integrated_native_masters_preserved','integrated_macro_placements_verified')}))

    def test_new_native_inventory_requires_all_630_actual_primitives(self):
        rows=['.subckt '+rc.NAME+'_flat '+' '.join(rc.physical.PORTS)]
        for model,count in rc.EXPECTED.items():
            for k in range(count):
                nodes='CLK VGND' if 'cap_mim' in model else 'CLK REQUEST VGND VGND'
                rows.append('X'+str(len(rows))+' '+nodes+' '+model+' w=1 l=0.15')
        rows.append('.ends '+rc.NAME+'_flat');text='\n'.join(rows)+'\n'
        self.assertEqual(rc.census(text)['native_primitives'],630)
        self.assertEqual(rc.census(text)['native_model_counts'],rc.EXPECTED)
        with self.assertRaisesRegex(ValueError,'inventory'):rc.census('\n'.join(rows[:1]+rows[2:])+'\n')

    def test_new_physical_gate_requires_exact_two_setters_and_native_master_witness(self):
        state=dict(status='complete',passed=True,qualified_phy=False);r=self.physical()
        rc.require_physical(state,r)
        for key in ('fast_clear_counter_physical_passed','same_phase_logic'):
            bad=deepcopy(r);bad[key]=False
            with self.assertRaises(ValueError):rc.require_physical(state,bad)
        bad=deepcopy(r);bad['physical']['native_master_witness']['all_integrated_native_masters_preserved']=False
        with self.assertRaisesRegex(ValueError,'native master'):rc.require_physical(state,bad)

    def test_replay_preserves_original_twelve_specs_and_complete_native_fixture(self):
        self.assertEqual(transient.specifications(),original.specifications());self.assertEqual(transient.NATIVE_MOS,644)
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            for spec in transient.specifications():
                new=transient.fixture(Path('/fixture'),spec,[])
                old=original.fixture(Path('/fixture'),spec,[])
                self.assertEqual(new.split('\n',1)[1],old.split('\n',1)[1])
                self.assertIn('.tran 1p 26n 0 1p',new)

    def test_followup_requires_explicit_new_physical_context(self):
        self.assertEqual(follow.PHYSICAL,'fast_clear_counter_physical_v267')
        self.assertEqual(follow.RC,rc.CONTEXT);self.assertEqual(follow.TRANSIENT,transient.CONTEXT)
        with self.assertRaisesRegex(ValueError,'physical artifact'):
            follow.require_source(follow.ROOT/'build/diagnostics/strong_storage_counter_physical_v234'/('a'*16))

    def test_actual_closed_native_gds_has_exact_new_inventory_and_witnesses(self):
        parent=rc.ROOT/'build/diagnostics/fast_clear_counter_physical_v267/5f2c400d640d10fb'
        if not (parent/'summary.json').exists():self.skipTest('Closed fast-clear physical artifact unavailable')
        report=json.loads((parent/'summary.json').read_text())
        rc.require_physical(json.loads((parent/'state.json').read_text()),report)
        reference=parent/rc.NAME/(rc.NAME+'.lvs.spice')
        census=rc.census(reference.read_text())
        self.assertEqual(census['ports'],rc.physical.PORTS)
        self.assertEqual({k:census[k] for k in report['native_census']},report['native_census'])
        self.assertTrue(all(rc.sha(parent/n)==h for n,h in report['files'].items()))


if __name__=='__main__':unittest.main()
