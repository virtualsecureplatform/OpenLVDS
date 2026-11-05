# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import parallel_final_bank_v100 as model


class ParallelFinalInverterTests(unittest.TestCase):
    def fixture(self):
        top = model.base.name('w084'); inv = model.INV
        return (f'.subckt {inv} A Y VGND VPWR\n'
                'XN Y A VGND VGND sky130_fd_pr__nfet_01v8_lvt w=.65 l=.15\n'
                f'.ends {inv}\n.subckt {top} IN OUT VPWR VGND\n'
                f'Xfine_driver selected OUT VGND VPWR {inv}\n.ends {top}\n')

    def test_additional_cell_shares_the_input_output_and_supplies(self):
        original = self.fixture()
        changed = model.parallel_driver(original, model.base.name('w084'), model.name('w084'))
        self.assertEqual(model.projection(changed, 'w084'), original)
        self.assertIn('Xfine_parallel selected OUT VGND VPWR '+model.INV, changed)
        self.assertEqual(len(model.source.native.definitions(changed)[model.name('w084')][1]), 2)

    def test_serial_or_wrong_supply_connection_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'wiring'):
            model.parallel_driver(self.fixture().replace('selected OUT VGND', 'selected buffer_raw VGND'), model.base.name('w084'), model.name('w084'))
        changed = model.parallel_driver(self.fixture(), model.base.name('w084'), model.name('w084'))
        with self.assertRaisesRegex(ValueError, 'rewired'):
            model.projection(changed.replace('Xfine_parallel selected OUT VGND VPWR', 'Xfine_parallel selected OUT VPWR VGND'), 'w084')

    def test_duplicate_application_is_rejected(self):
        changed = model.parallel_driver(self.fixture(), model.base.name('w084'), model.name('w084'))
        with self.assertRaisesRegex(ValueError, 'already'):
            model.parallel_driver(changed, model.name('w084'), 'another')


if __name__ == '__main__':
    unittest.main()
