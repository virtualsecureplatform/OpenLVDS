# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_strong_storage_counter_rc_v231 as p


class StrongStorageCounterRcAdmission(unittest.TestCase):
    def test_all_physical_and_name_repair_witnesses_required(self):
        state=dict(status='complete',passed=True,qualified_phy=False)
        r=dict(compact_counter_physical_passed=True,same_phase_logic=True,strong_native_storage_and_request=True,request_drivers=2,physical=dict(passed=True,drc_count='0',lvs_passed=True,macro_count=22,
               native_master_witness={k:True for k in ('all_shared_native_masters_identical','all_integrated_native_masters_preserved','integrated_macro_placements_verified')}))
        p.require_physical(state,r)
        for key in r['physical']['native_master_witness']:
            changed=deepcopy(r);changed['physical']['native_master_witness'][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):p.require_physical(state,changed)
        for key in ('compact_counter_physical_passed','same_phase_logic','strong_native_storage_and_request'):
            changed=deepcopy(r);changed[key]=False
            with self.assertRaises(ValueError):p.require_physical(state,changed)
        changed=deepcopy(r);changed['physical']['macro_count']=20
        with self.assertRaises(ValueError):p.require_physical(state,changed)
        with self.assertRaises(ValueError):p.require_physical(dict(state,status='running'),r)
        changed=deepcopy(r);changed['physical']['drc_count']='1'
        with self.assertRaises(ValueError):p.require_physical(state,changed)

    def test_old_21_macro_inventory_is_rejected_and_strong_native_counts_required(self):
        rows=['.subckt '+p.NAME+'_flat '+' '.join(p.physical.PORTS)]
        for model,count in p.EXPECTED.items():
            for k in range(count):
                nodes='CLK VGND' if 'cap_mim' in model else 'CLK REQUEST VGND VGND'
                rows.append('X'+str(len(rows))+' '+nodes+' '+model+' w=1 l=.15')
        rows.append('.ends');text='\n'.join(rows)+'\n';r=p.census(text)
        self.assertEqual(r['native_primitives'],598);self.assertEqual(r['native_model_counts'],p.EXPECTED)
        with self.assertRaises(ValueError):p.census(text.replace('sky130_fd_pr__nfet_01v8','sky130_fd_pr__nfet_01v8_lvt',1))
        reference=p.ROOT/'build/diagnostics/repaired_clock_counter_physical_v191/e2af7f307ddb041d'/p.NAME/(p.NAME+'.lvs.spice')
        if reference.exists():
            with self.assertRaises(ValueError):p.census(reference.read_text())

    def test_actual_new_22_macro_lvs_has_all_598_native_primitives(self):
        reference=p.ROOT/'build/diagnostics/strong_storage_counter_physical_v234/a3c3c8188cdb61a3'/p.NAME/(p.NAME+'.lvs.spice')
        if not reference.exists():self.skipTest('requires actual closed strong-storage counter GDS/LVS')
        result=p.census(reference.read_text());self.assertEqual(result['native_primitives'],598);self.assertEqual(result['native_model_counts'],p.EXPECTED)

    def test_streaming_hash_is_complete_byte_sha256_across_block_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'native.raw'
            for data in (b'',b'a',(bytes(range(256))*8193)+b'end'):
                path.write_bytes(data);self.assertEqual(p.sha(path),hashlib.sha256(data).hexdigest())


if __name__=='__main__':unittest.main()
