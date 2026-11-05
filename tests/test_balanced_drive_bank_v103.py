# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import balanced_drive_bank_v103 as model


class BalancedUpstreamTests(unittest.TestCase):
    def fixture(self):
        top = model.base.name('w126'); tg = model.TG; inv = model.INV
        rows = [f'.subckt {tg} A Z EN ENB VPWR VGND',
                'XN A EN Z VGND sky130_fd_pr__nfet_01v8_lvt w=1.68 l=.15', f'.ends {tg}',
                f'.subckt {inv} A Y VGND VPWR',
                'XP Y A VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15', f'.ends {inv}',
                f'.subckt {top} IN OUT VPWR VGND']
        for g in range(4):
            for leaf in range(4):
                k = 4*g+leaf; tap = 'IN' if k == 0 else f'tap{k}'
                rows.append(f'Xswitch0_{g}_{leaf} {tap} tree0_{g} en0_{leaf} en_b0_{leaf} VPWR VGND {tg}')
            rows.append(f'Xgroup_inverse{g} tree0_{g} regenerated{g} VGND VPWR {inv}')
        return '\n'.join(rows+[f'.ends {top}', ''])

    def test_first_muxes_and_group_inverters_are_duplicated_with_exact_projection(self):
        original = self.fixture()
        changed = model.parallel_upstream(original, model.base.name('w126'), model.name('w126'))
        self.assertEqual(model.projection(changed, 'w126'), original)
        body = model.source.native.definitions(changed)[model.name('w126')][1]
        self.assertEqual(sum(w[0].startswith('Xleaf_parallel') for w in body), 16)
        self.assertEqual(sum(w[0].startswith('Xgroup_parallel') for w in body), 4)

    def test_wrong_leaf_control_and_group_connection_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'First mux'):
            model.parallel_upstream(self.fixture().replace('tap5 tree0_1 en0_1', 'tap5 tree0_1 en0_0'), model.base.name('w126'), model.name('w126'))
        changed = model.parallel_upstream(self.fixture(), model.base.name('w126'), model.name('w126'))
        bad = changed.replace('Xgroup_parallel2 tree0_2 regenerated2', 'Xgroup_parallel2 tree0_2 regenerated1')
        with self.assertRaisesRegex(ValueError, 'rewired'):
            model.projection(bad, 'w126')

    def test_duplicate_application_is_rejected(self):
        changed = model.parallel_upstream(self.fixture(), model.base.name('w126'), model.name('w126'))
        with self.assertRaisesRegex(ValueError, 'already'):
            model.parallel_upstream(changed, model.name('w126'), 'another')


if __name__ == '__main__':
    unittest.main()
