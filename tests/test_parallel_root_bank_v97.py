# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import parallel_root_bank_v97 as model


class ParallelRootCircuitTests(unittest.TestCase):
    def fixture(self):
        top = model.base.name('w084'); tg = model.TG
        rows = [f'.subckt {tg} A Z EN ENB VPWR VGND',
                'XN A EN Z VGND sky130_fd_pr__nfet_01v8_lvt w=1.68 l=.15',
                'XP A ENB Z VPWR sky130_fd_pr__pfet_01v8 w=3.36 l=.15', f'.ends {tg}',
                f'.subckt {top} IN OUT VPWR VGND']
        rows += [f'Xswitch1_0_{k} regenerated{k} selected en1_{k} en_b1_{k} VPWR VGND {tg}' for k in range(4)]
        return '\n'.join(rows+[f'.ends {top}', ''])

    def test_all_four_branches_duplicate_without_another_serial_stage(self):
        original = self.fixture(); top = model.name('w084')
        changed = model.parallel_roots(original, model.base.name('w084'), top)
        self.assertEqual(model.projection(changed, 'w084'), original)
        ports, body = model.source.native.definitions(changed)[top]
        self.assertEqual(len(body), 8)
        for k in range(4):
            self.assertIn(f'Xroot_parallel{k} regenerated{k} selected en1_{k} en_b1_{k} VPWR VGND', changed)

    def test_wrong_branch_or_control_connection_is_rejected(self):
        original = self.fixture()
        with self.assertRaisesRegex(ValueError, 'wiring'):
            model.parallel_roots(original.replace('regenerated2 selected', 'regenerated1 selected'), model.base.name('w084'), model.name('w084'))
        changed = model.parallel_roots(original, model.base.name('w084'), model.name('w084'))
        bad = changed.replace('Xroot_parallel2 regenerated2 selected en1_2', 'Xroot_parallel2 regenerated2 selected en1_1')
        with self.assertRaisesRegex(ValueError, 'rewired'):
            model.projection(bad, 'w084')

    def test_duplicate_parallel_application_is_rejected(self):
        changed = model.parallel_roots(self.fixture(), model.base.name('w084'), model.name('w084'))
        with self.assertRaisesRegex(ValueError, 'already'):
            model.parallel_roots(changed, model.name('w084'), 'another')


if __name__ == '__main__':
    unittest.main()
