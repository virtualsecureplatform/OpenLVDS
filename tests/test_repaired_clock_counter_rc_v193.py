# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_repaired_clock_counter_rc_v193 as p


class CounterRcAdmission(unittest.TestCase):
    def test_all_physical_and_name_repair_witnesses_required(self):
        state=dict(status='complete',passed=True,qualified_phy=False)
        r=dict(physical_name_repair_passed=True,physical=dict(passed=True,drc_count='0',lvs_passed=True),
               unchanged_geometry={k:True for k in ('exact_cell_name_bijection','all_masks_identical','all_labels_identical','all_child_and_root_placements_identical')},
               native_master_witness={k:True for k in ('all_shared_native_masters_identical','all_integrated_native_masters_preserved','integrated_macro_placements_verified')})
        p.require_physical(state,r)
        for section in ('unchanged_geometry','native_master_witness'):
            for key in r[section]:
                changed=deepcopy(r);changed[section][key]=False
                with self.subTest(section=section,key=key),self.assertRaises(ValueError):p.require_physical(state,changed)
        for key,value in [('physical_name_repair_passed',False)]:
            changed=deepcopy(r);changed[key]=value
            with self.assertRaises(ValueError):p.require_physical(state,changed)
        with self.assertRaises(ValueError):p.require_physical(dict(state,status='running'),r)
        changed=deepcopy(r);changed['physical']['drc_count']='1'
        with self.assertRaises(ValueError):p.require_physical(state,changed)

    def test_actual_full_counter_native_inventory_and_models(self):
        reference=p.ROOT/'build/diagnostics/repaired_clock_counter_physical_v191/e2af7f307ddb041d'/p.NAME/(p.NAME+'.lvs.spice')
        if not reference.exists():self.skipTest('requires retained actual 21-macro counter LVS')
        text=reference.read_text();r=p.census(text)
        self.assertEqual(r['native_primitives'],494);self.assertEqual(r['native_model_counts'],p.EXPECTED)
        self.assertEqual(r['ports'],p.physical.source.PORTS)
        with self.assertRaises(ValueError):p.census(text.replace('sky130_fd_pr__nfet_01v8','sky130_fd_pr__nfet_01v8_lvt',1))

    def test_streaming_hash_is_complete_byte_sha256_across_block_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'native.raw'
            for data in (b'',b'a',(bytes(range(256))*8193)+b'end'):
                path.write_bytes(data);self.assertEqual(p.sha(path),hashlib.sha256(data).hexdigest())


if __name__=='__main__':unittest.main()
