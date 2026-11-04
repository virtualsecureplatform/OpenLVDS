# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import layout
import weighted_fine_unit_v2 as unit
import build_weighted_fine_units_v3 as physical


class WeightedFinePhysicalTests(unittest.TestCase):
    def test_all_five_schematics_preserve_the_existing_root_devices(self):
        original = layout.circuits(unit.fine.fine_cells('root'))
        for bit in range(5):
            name = unit.name(bit)
            ports, devices = layout.flatten(layout.circuits(unit.schematic(bit)), name)
            old_ports, old_devices = layout.flatten(original, f'weighted_root_{bit}')
            self.assertEqual(ports, old_ports)
            self.assertEqual(len(devices), 5)
            for new, old in zip(devices, old_devices):
                self.assertEqual(new['model'], old['model'])
                self.assertEqual(new['params'], old['params'])
                self.assertEqual([n.replace(name, 'CELL') for n in new['nodes']],
                                 [n.replace(f'weighted_root_{bit}', 'CELL') for n in old['nodes']])

    def test_largest_plate_escapes_do_not_short_or_crowd_signal_columns(self):
        # Native 8x12/2x2 MIM and 1.68/3.36 um MOS PCell bounds from
        # the first layout that exposed CAP/ENB and CAP/VSS shorts.
        _, devices = layout.flatten(layout.circuits(unit.schematic(4)), unit.name(4))
        boxes = [(-1.055, -1.735, 1.055, 1.735),
                 (-1.055, -2.6, 1.055, 2.6),
                 (-1.055, -1.735, 1.055, 1.735),
                 (-5.08, -6.2, 5.08, 6.2),
                 (-2.08, -1.2, 2.08, 1.2)]
        library = {layout.primitive_key(d): ('fixture', {'bbox': box})
                   for d, box in zip(devices, boxes)}
        plan = physical.plan(library, devices)
        # Separate horizontal M4 escapes need >=0.3 um edge clearance.
        self.assertGreaterEqual(plan['cap_escape_y'][1] - plan['cap_escape_y'][0] - .6, .3)
        for center, box, escape in zip(plan['cap_centers'], boxes[3:], plan['cap_escape_y']):
            self.assertGreater(escape - center[1] - box[3], 1.34)
        bottom = plan['bottom_via_x'][0]
        self.assertAlmostEqual(bottom, 19.8)  # CLR source is already VSS.
        for x in (18.2, 19.):  # CLR drain CAP and gate ENB.
            self.assertGreaterEqual(abs(bottom - x), .5)

    def test_unknown_bit_is_rejected(self):
        for bit in (-1, 5):
            with self.assertRaises(ValueError):
                unit.schematic(bit)
