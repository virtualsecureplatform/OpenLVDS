# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import driver_geometric_shape as candidate
import probe_stronger_driver_shape as reference
from driver_current_variant import source_variant
from driver_gate_taper import transform
from layout import circuits


class CalculatedGeometricTaper(unittest.TestCase):
    def source(self):
        return reference.shaped(transform(source_variant((reference.ROOT / 'analog/openlvds.spice').read_text()), reference.VARIANT))

    def test_only_intermediate_units_and_two_output_cap_sizes_change(self):
        before = circuits(self.source())
        after = circuits(candidate.transform(self.source()))
        self.assertEqual(set(after), (set(before) - {candidate.OLD}) | {candidate.NEW})
        for name, block in before.items():
            if name not in [candidate.OLD, candidate.taper.TOP]:
                self.assertEqual(block, after[name])
        old, new = [{r[0]: r for r in definitions[candidate.taper.TOP][1]} for definitions in [before, after]]
        self.assertEqual(old.keys(), new.keys())
        for name, row in old.items():
            if name == 'XLS':
                self.assertEqual(new[name], (row[0], row[1], candidate.NEW, row[3]))
            elif name in ['XCOUTP', 'XCOUTN']:
                self.assertEqual(new[name], (row[0], row[1], row[2], dict(w='36', l='36')))
            else:
                self.assertEqual(row, new[name])
        old_rows = before[candidate.OLD][1]
        new_rows = after[candidate.NEW][1]
        self.assertEqual(new_rows, [r for r in old_rows if r[0] not in ['XB0_S1_3', 'XB1_S1_3']])
        for branch in [0, 1]:
            for stage, count in enumerate(candidate.COUNTS):
                self.assertEqual(len([r for r in new_rows if r[0].startswith(f'XB{branch}_S{stage}_')]), count)

    def test_changed_reference_or_repeat_transform_is_rejected(self):
        source = self.source()
        for bad in [source.replace('w=30 l=30', 'w=35 l=35'), candidate.transform(source),
                    source.replace('XB0_S1_3 G0_0', 'XB0_S1_3 DIFFERENT')]:
            with self.assertRaises(ValueError):
                candidate.transform(bad)


if __name__ == '__main__':
    unittest.main()
