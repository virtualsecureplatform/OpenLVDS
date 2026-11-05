# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_tg_terminated_v6 as circuit


class NativeTailTerminationTests(unittest.TestCase):
    def orders(self):
        result = {}
        for cell in circuit.previous.instances(circuit.PROFILE):
            model = cell['model']; pins = dict(dict(VPWR='', VPB='', VGND='', VNB=''), **cell['pins'])
            if model in (circuit.previous.INVERTER, circuit.previous.BUFFER):
                pins.pop('VPB'); pins.pop('VNB')
            elif model in (circuit.previous.FINE, circuit.previous.tg_name(circuit.PROFILE)):
                pins = cell['pins']
            result[model] = sorted(pins)
        return result

    def test_exactly_one_real_mim_is_added_without_changing_any_active_component(self):
        for coarse in (16, 32, 64, 128, 256):
            for fine in (16, 32):
                old = circuit.previous.instances(circuit.PROFILE, coarse, fine)
                new = circuit.instances(coarse, fine)
                self.assertEqual(new[:-1], old)
                self.assertEqual(new[-1], dict(name='tail_termination', model=circuit.CAP,
                    pins=dict(TOP='unused_tail', BOTTOM='VGND'), parameters=dict(w=2, l=2)))
                self.assertEqual(next(c for c in new if c['name'] == 'tail_load')['pins']['A'], f'tap{coarse-1}')

    def test_native_spice_body_and_public_ports_are_identical_except_the_termination(self):
        orders = self.orders()
        for coarse in (16, 32, 64, 128, 256):
            for fine in (16, 32):
                old = circuit.previous.source(orders, circuit.PROFILE, coarse, fine)
                new = circuit.source(orders, coarse, fine)
                old_def = circuit.previous.dimensions.native.definitions(old)[circuit.previous.name(circuit.PROFILE, coarse, fine)]
                new_def = circuit.previous.dimensions.native.definitions(new)[circuit.name(coarse, fine)]
                self.assertEqual(new_def[0], old_def[0])
                self.assertEqual(new_def[1][:-1], old_def[1])
                self.assertEqual(new_def[1][-1], ['Xtail_termination', 'unused_tail', 'VGND', circuit.CAP, 'w=2', 'l=2'])
                self.assertNotIn('delay=', new)


if __name__ == '__main__':
    unittest.main()
