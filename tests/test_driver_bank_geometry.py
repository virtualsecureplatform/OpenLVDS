# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import driver_bank_geometry as geometry
from layout import Geometry, GRID, circuits


class ConnectedFingerBankGeometry(unittest.TestCase):
    def test_tight_vias_keep_exact_cut_sizes_on_fractional_requested_positions(self):
        g = Geometry()
        geometry.via12(g, .123456, -.411111)
        geometry.via23(g, .123456, -.411111)
        for layer, size in [('via1', .15), ('via2', .20)]:
            rect = g.layers[layer][0]
            self.assertEqual((rect[2] - rect[0], rect[3] - rect[1]), (round(size / GRID), round(size / GRID)))

    def test_every_original_finger_remains_in_reference_and_all_four_ports_export(self):
        ports = {'B': ('psubdiffcont', 0., -4.785)}
        for i, x in enumerate([-1.575, -.525, .525, 1.575]):
            ports['G' + str(i)] = ('polycont', x, -4.275 if i % 2 == 0 else 4.275)
            ports['D' + str(i)] = ('ndiffc', x - .24, 0.)
            ports['S' + str(i)] = ('ndiffc', x + .24, 0.)
        info = dict(ports=ports, bbox=[-2.65, -5.05, 2.65, 5.05])
        parameters = dict(model='sky130_fd_pr__nfet_01v8', w='8', l='.15', nf=4)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = geometry.write(out, 'bank', 'primitive', info, parameters)
            self.assertEqual(set(result['ports']), {'D', 'G', 'S', 'B'})
            parsed = circuits((out / 'bank.sch.spice').read_text())['bank']
            self.assertEqual(parsed[0], ['D', 'G', 'S', 'B'])
            self.assertEqual(len(parsed[1]), 4)
            for row in parsed[1]:
                self.assertEqual(row[1:], (['D', 'G', 'S', 'B'], parameters['model'], dict(w='8', l='.15')))
            text = (out / 'bank.mag').read_text()
            self.assertEqual(text.count('\nport '), 4)
            self.assertIn('use primitive I0', text)


if __name__ == '__main__':
    unittest.main()
