# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_public_port_order_v171 import canonicalize
import complete_component_reference_v247 as references
import native_bank_inventory_v51 as native

ROOT=Path(__file__).resolve().parents[1]
RETAINED=ROOT/'build/diagnostics/isolated_bank_standard_references_v248/4047596d2460c6e9/sky130_fd_sc_hd__buf_4'

@unittest.skipUnless(RETAINED.exists(),'Retained native standard master extraction required')
class NativeStandardHeaderTests(unittest.TestCase):
    def test_real_standard_header_permutation_preserves_native_body(self):
        model='sky130_fd_sc_hd__buf_4';source=(RETAINED/(model+'.sch.spice')).read_text()
        raw=re.sub(r'\n[ \t]*\+[ \t]*',' ',(RETAINED/(model+'.lvs.spice')).read_text())
        ports,expected=native.native_leaves(source,model)
        fixed,proof=canonicalize(raw,model+'_flat',ports)
        self.assertTrue(proof['all_nonheader_bytes_preserved'])
        self.assertTrue(proof['named_public_port_bijection_verified'])
        self.assertTrue(proof['header_changed'])
        _,actual=native.native_leaves(fixed,model+'_flat')
        self.assertTrue(native.compare_parameters(expected,actual)['native_parameters_preserved'])
        result,reference_proof=references.complete(source,{model:fixed},{model:ports})
        _,restored=native.native_leaves(result,model)
        self.assertEqual(restored,actual)
        self.assertFalse(reference_proof[model]['junction_values_inferred'])

    def test_same_count_but_changed_pin_name_is_not_a_permutation(self):
        model='sky130_fd_sc_hd__buf_4';source=(RETAINED/(model+'.sch.spice')).read_text()
        raw=re.sub(r'\n[ \t]*\+[ \t]*',' ',(RETAINED/(model+'.lvs.spice')).read_text())
        ports,_=native.native_leaves(source,model)
        with self.assertRaisesRegex(ValueError,'exact named bijection'):
            canonicalize(raw,model+'_flat',[*ports[:-1],'OTHER'])

if __name__=='__main__':unittest.main()
