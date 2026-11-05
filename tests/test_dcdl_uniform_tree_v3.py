# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_uniform_tree_v3 as circuit


class UniformTreeTests(unittest.TestCase):
    def test_every_code_selects_the_corresponding_tap_at_equal_mux_depth(self):
        for count in (16, 32, 64, 128, 256):
            cells = circuit.instances(count)
            muxes = [c for c in cells if c['name'].startswith('mux')]
            depths = []
            for code in range(count):
                controls = circuit.encode(code, 0, count)
                values = {f'tap{i}': (i, 0) for i in range(count)}
                values.update({f'select{i}': controls[f'S{i}']
                               for i in range(count.bit_length()-1)})
                for cell in muxes:
                    p = cell['pins']
                    index = values[p['S']] if 'S' in p else values[p['S0']]+2*values[p['S1']]
                    tap, depth = values[p[f'A{index}']]
                    values[p['X']] = (tap, depth+1)
                self.assertEqual(values['selected'][0], code)
                depths.append(values['selected'][1])
            self.assertEqual(len(set(depths)), 1)

    def test_fine_carries_add_exactly_one_identical_unit(self):
        for fine_count in (16, 32):
            cells = circuit.instances(fine_count=fine_count)
            units = [c for c in cells if c['model'] == circuit.fine.NAME]
            self.assertEqual(len(units), fine_count-1)
            self.assertTrue(all(c['pins']['NODE'] == 'selected' for c in units))
            previous = set()
            for code in range(fine_count):
                active = {pin for pin, value in circuit.encode(0, code, fine_count=fine_count).items()
                          if pin.startswith('E') and value}
                self.assertEqual(len(active), code)
                if code:
                    self.assertEqual(len(active-previous), 1)
                    self.assertFalse(previous-active)
                previous = active

    def test_all_taps_have_equal_direct_fanout(self):
        cells = circuit.instances()
        fanout = {f'tap{i}': 0 for i in range(16)}
        for cell in cells:
            for pin, node in cell['pins'].items():
                if pin.startswith('A') and node in fanout:
                    fanout[node] += 1
        self.assertEqual(set(fanout.values()), {2})

    def test_interface_order_is_explicit_and_missing_or_duplicate_pins_rejected(self):
        orders = {}
        for cell in circuit.instances():
            pins = dict(VPWR='', VPB='', VGND='', VNB='', **cell['pins'])
            if cell['model'] == circuit.BUFFER:
                pins = dict(A='', X='', VPWR='', VGND='')
            elif cell['model'] == circuit.fine.NAME:
                pins = cell['pins']
            orders[cell['model']] = sorted(pins, reverse=True)
        text = circuit.source(orders)
        self.assertNotIn('delay=', text)
        self.assertEqual(text.count('\nX'), len(circuit.instances()))
        model = circuit.BUFFER
        good = orders[model]
        for bad in ([], good+['A'], good[:-1], good+['UNKNOWN']):
            with self.subTest(order=bad):
                with self.assertRaises(ValueError):
                    circuit.source(dict(orders, **{model: bad}))

    def test_undeclared_dimensions_and_codes_rejected(self):
        for coarse, fine in ((8, 32), (16, 64), (16.0, 32)):
            with self.assertRaises(ValueError):
                circuit.instances(coarse, fine)
        for coarse, fine in ((-1, 0), (16, 0), (0, 32), (True, 0)):
            with self.assertRaises(ValueError):
                circuit.encode(coarse, fine)


if __name__ == '__main__':
    unittest.main()
