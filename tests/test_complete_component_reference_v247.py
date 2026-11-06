# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import json
import re
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import complete_component_reference_v247 as reference
import native_bank_inventory_v51 as native
from build_compound_drivers_v3 import cell_definition

OLD='''.subckt child A Y VGND VPWR
XN Y A VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15
XP Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15
.ends child
.subckt driver A Y VGND VPWR
Xgate A Y VGND VPWR child
.ends driver
.subckt other A Y
.ends other
.subckt bank IN OUT VPWR VGND
XD IN OUT VPWR VGND driver
.ends bank
'''
ACTUAL='''.subckt driver_flat A Y VPWR VGND
X0 Y A VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15 ad=.1 as=.2 pd=1 ps=2
X1 Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15 ad=.3 as=.4 pd=3 ps=4
.ends driver_flat
'''
ORDERS=dict(driver=['A','Y','VPWR','VGND'],other=['A','Y'])

class CompleteReferenceTests(unittest.TestCase):
    def test_qualified_flat_reference_fixes_header_order_without_rewiring_root(self):
        result,proof=reference.complete(OLD,dict(driver=ACTUAL),ORDERS)
        self.assertEqual(native.layout.circuits(result)['driver'][0],ORDERS['driver'])
        self.assertEqual(cell_definition(result,'bank'),cell_definition(OLD,'bank'))
        self.assertEqual(cell_definition(result,'child'),cell_definition(OLD,'child'))
        self.assertEqual(cell_definition(result,'other'),cell_definition(OLD,'other'))
        _,devices=native.native_leaves(result,'bank')
        n=next(d for d in devices if d['model']=='sky130_fd_pr__nfet_01v8')
        self.assertEqual(n['nodes'],['OUT','IN','VGND','VGND'])
        p=next(d for d in devices if d['model']=='sky130_fd_pr__pfet_01v8')
        self.assertEqual(p['nodes'],['OUT','IN','VPWR','VPWR'])
        self.assertFalse(proof['driver']['junction_values_inferred'])
        self.assertEqual(proof['driver']['newly_characterized_junction_devices'],2)
        self.assertEqual(proof['driver']['original_schematic_ports'],['A','Y','VGND','VPWR'])

    def test_dimension_changes_or_missing_junction_fields_are_rejected(self):
        for actual in [ACTUAL.replace('w=.65','w=.66'),ACTUAL.replace(' ad=.1','')]:
            with self.assertRaises(ValueError):reference.complete(OLD,dict(driver=actual),ORDERS)

    def test_changed_or_duplicate_port_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'pin names'):
            reference.complete(OLD,dict(driver=ACTUAL.replace('A Y VPWR VGND','A Y VPWR BAD')),ORDERS)
        with self.assertRaisesRegex(ValueError,'pin names'):
            reference.complete(OLD,dict(driver=ACTUAL),dict(ORDERS,driver=['A','Y','VGND','VGND']))

    def test_other_native_definition_order_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'emitted graph instance order'):
            reference.complete(OLD,dict(driver=ACTUAL),dict(ORDERS,other=['Y','A']))

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/diagnostics/isolated_fine_placement_v238/da8cd048ac28c378'
VIEWS=ROOT/'build/diagnostics/isolated_fine_cell_views_v236/b040d127238a22fa/native'
STANDARDS=ROOT/'build/diagnostics/isolated_bank_standard_references_v250/70e0b0dbd0180169'
ACTUAL_BANK=ROOT/'build/diagnostics/isolated_fine_bank_junctions_v243/2ae01c1174cfa236/ordinary/openlvds_isolated_fine_physical_v239.lvs.spice'

@unittest.skipUnless((STANDARDS/'summary.json').exists() and ACTUAL_BANK.exists(),'Native bank and standard-master evidence required')
class CompleteNativeBankTests(unittest.TestCase):
    def inputs(self,standards):
        i=json.loads((BASE/'manifest.json').read_text())['identity']
        models=['openlvds_discharge_p20n16_registered_v236','openlvds_buf_8_o4_registered_v236']
        extra={m:(VIEWS/m/(m+'.lvs.spice')).read_text() for m in models}
        if standards:
            r=json.loads((STANDARDS/'summary.json').read_text())
            self.assertTrue(r['native_standard_references_passed'])
            extra.update({row['model']:(STANDARDS/row['model']/row['native_reference_file']).read_text() for row in r['rows']})
        result,proof=reference.complete((BASE/'reference.spice').read_text(),extra,i['graph']['orders'])
        actual=re.sub(r'\n[ \t]*\+[ \t]*',' ',ACTUAL_BANK.read_text())
        return i,result,actual,proof

    def test_all_1479_mos_and_43_mim_preserve_supplied_junctions(self):
        import isolated_fine_bank_inventory_v244 as inventory
        i,result,actual,proof=self.inputs(True)
        r=inventory.verify(result,i['graph']['top'],actual,i['graph']['top']+'_flat')
        self.assertEqual(r['newly_characterized_junction_devices'],155) # only original fine devices remain for geometry allocation
        self.assertEqual(r['native_primitives'],1522)
        self.assertTrue(r['all_reference_supplied_junctions_preserved'])
        self.assertEqual(len(proof),7)
        self.assertTrue(all(not p['junction_values_inferred'] for p in proof.values()))

    def test_omitting_standard_master_references_still_fails_strictly(self):
        import isolated_fine_bank_inventory_v244 as inventory
        i,result,actual,proof=self.inputs(False)
        with self.assertRaisesRegex(ValueError,'Ambiguous partial-junction native class'):
            inventory.verify(result,i['graph']['top'],actual,i['graph']['top']+'_flat')


if __name__=='__main__':unittest.main()
