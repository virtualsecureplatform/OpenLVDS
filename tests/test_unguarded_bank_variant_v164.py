# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unguarded_bank_variant_v164 as p


class OutputOnlyBankRevisionTests(unittest.TestCase):
    def fixture(self):
        inv=[f'.subckt {p.SCHEM_INV} A Y VGND VPWR']
        inv += [f'X{k} Y A VGND VGND sky130_fd_pr__nfet_01v8_lvt w=.65 l=.15 ad=.1 as=.1 pd=1 ps=1' for k in range(17) if k!=8]
        inv += ['X8 Y VGND sky130_fd_pr__cap_mim_m3_1 l=2 w=2','.ends']
        pair=[f'.subckt {p.PAIR} A Y VPWR VGND',f'Xinv0 A Y VGND VPWR {p.SCHEM_INV}',f'Xinv1 A Y VGND VPWR {p.SCHEM_INV}','.ends']
        bank=[f'.subckt {p.TOP} IN OUT VPWR VGND',f'Xfine_compound selected OUT VPWR VGND {p.PAIR}']
        bank += [f'Xgroup_compound{k} IN group{k} VPWR VGND {p.PAIR}' for k in range(4)]
        bank += [f'Xextra{k} IN IN VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15' for k in range(1293)]
        bank += [f'Xtail{k} IN VGND sky130_fd_pr__cap_mim_m3_1 l=2 w=2' for k in range(32)]
        return '\n'.join(inv+pair+bank+['.ends'])+'\n'

    def test_shared_coarse_cells_keep_guards_and_all_original_native_cards(self):
        source=self.fixture();result,proof=p.schematic(source)
        self.assertEqual(proof['native_mos'],1453);self.assertEqual(proof['native_mims'],40)
        self.assertEqual(len(proof['removed_output_guards']),2)
        for k in range(4):self.assertIn(f'Xgroup_compound{k} IN group{k} VPWR VGND {p.PAIR}\n',result)
        self.assertIn(p.cell_definition(source,p.SCHEM_INV),result)
        self.assertIn(p.cell_definition(source,p.PAIR),result)
        self.assertIn('Xfine_compound selected OUT VPWR VGND '+p.NEW_PAIR,result)
        self.assertFalse(proof['qualified_phy'])

    def test_wrong_target_guard_or_inventory_is_rejected(self):
        source=self.fixture()
        for wrong in (source.replace('Xfine_compound','Xother'),source.replace('X8 Y VGND','X8 A VGND'),
                      source.replace('l=2 w=2','l=3 w=2',1),source.replace('Xextra1292 IN','* removed IN')):
            with self.assertRaises(ValueError):p.schematic(wrong)


if __name__=='__main__':unittest.main()
