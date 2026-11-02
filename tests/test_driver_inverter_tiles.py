# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_driver_inverter_tiles import inverter_pairs
import driver_finger_banks as banks
import driver_geometric_shape as recipe
import probe_stronger_driver_shape as seed
from driver_current_variant import source_variant
from driver_gate_taper import transform
from layout import circuits, flatten
from probe_driver_finger_pcells import key


class DriverInverterSelection(unittest.TestCase):
    def test_all_original_inverters_selected_once_without_bridge_or_mirror(self):
        text = recipe.transform(seed.shaped(transform(source_variant(
            (seed.ROOT / 'analog/openlvds.spice').read_text()), seed.VARIANT)))
        grouped = banks.group(flatten(circuits(text), recipe.taper.TOP)[1])
        before = deepcopy(grouped)
        pairs = inverter_pairs(grouped)
        self.assertEqual(len(pairs), 9)
        self.assertEqual(len({tuple(key(x) for x in pair) for pair in pairs}), 5)
        self.assertEqual(len({x['name'] for pair in pairs for x in pair}), 18)
        self.assertTrue(all('__XLS__' in x['name'] for pair in pairs for x in pair))
        self.assertEqual(grouped, before)

    def test_ambiguous_pull_down_rejected(self):
        devices = [dict(model='pfet', nodes=['Y', 'A', 'VDDIO', 'VDDIO']),
                   dict(model='nfet', nodes=['Y', 'A', 'VSS', 'VSS']),
                   dict(model='nfet', nodes=['Y', 'A', 'VSS', 'VSS'])]
        with self.assertRaises(ValueError):
            inverter_pairs(devices)


if __name__ == '__main__':
    unittest.main()
