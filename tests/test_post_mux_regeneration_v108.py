# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import post_mux_regeneration_v108 as model


class PostMuxRegenerationTests(unittest.TestCase):
    def fixture(self):
        top=model.base.name('w126');tg=model.TG;inv=model.INV;unit=top+'_unit'
        rows=[f'.subckt {tg} A Z EN ENB VPWR VGND',f'.ends {tg}',
              f'.subckt {inv} A Y VGND VPWR',f'.ends {inv}',
              f'.subckt {unit} NODE EN ENB VDD VSS',f'.ends {unit}',
              f'.subckt {top} IN OUT VPWR VGND']
        rows += [f'Xswitch1_0_{g} regenerated{g} selected en1_{g} en_b1_{g} VPWR VGND {tg}' for g in range(4)]
        rows.append(f'Xfine_driver selected OUT VGND VPWR {inv}')
        rows += [f'Xfine_unit{k} selected fine{k} fine_b{k} VPWR VGND {unit}' for k in range(31)]
        rows.append('Xtail tap15 VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2')
        rows += [f'Xgroup_inverse{g} tree0_{g} regenerated{g} VGND VPWR {inv}' for g in range(4)]
        return '\n'.join(rows+[f'.ends {top}',''])

    def changed(self):
        return model.rename(model.rewrite_body(self.fixture(),model.base.name('w126')),model.base.name('w126'),model.name('w126'))

    def test_fine_load_is_on_active_regenerator_output_and_projection_is_exact(self):
        original=self.fixture();changed=self.changed()
        self.assertEqual(model.projection(changed,'w126'),original)
        self.assertIn('Xbank_regenerator selected fine_slow VGND VPWR '+model.INV,changed)
        self.assertIn('Xfine_parallel fine_slow OUT VGND VPWR '+model.INV,changed)
        for g in range(4):self.assertIn(f'Xswitch1_0_{g} tree0_{g} selected',changed)
        for k in range(31):self.assertIn(f'Xfine_unit{k} fine_slow fine{k} fine_b{k}',changed)
        self.assertNotIn('Xgroup_inverse',changed)
        self.assertIn('Xtail tap15 VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2',changed)

    def test_wrong_root_or_fine_data_wiring_is_rejected(self):
        bad=self.fixture().replace('Xswitch1_0_2 regenerated2 selected','Xswitch1_0_2 regenerated1 selected')
        with self.assertRaisesRegex(ValueError,'Root mux'):model.rewrite_body(bad,model.base.name('w126'))
        bad=self.changed().replace('Xfine_unit0 fine_slow','Xfine_unit0 selected')
        with self.assertRaisesRegex(ValueError,'Fine-bank'):model.projection(bad,'w126')

    def test_wrong_common_inverter_connection_is_rejected(self):
        bad=self.changed().replace('Xbank_regenerator selected fine_slow','Xbank_regenerator OUT fine_slow')
        with self.assertRaisesRegex(ValueError,'Common inverter'):model.projection(bad,'w126')


if __name__=='__main__':unittest.main()
