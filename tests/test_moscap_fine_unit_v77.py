# SPDX-License-Identifier: GPL-3.0-only
"""Keep the new physical schematic equivalent to the simulated topology."""
from collections import Counter
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import layout
import mim_switch_2x3_v2 as old
import moscap_fine_bank_v75 as prototype
import moscap_fine_unit_v77 as physical


def signature(text, top):
    ports, devices = layout.flatten(layout.circuits(text), top)
    rows = []
    for d in devices:
        nodes = [n if n in ports else 'private_cap' for n in d['nodes']]
        if 'fet_' in d['model']:
            # Source/drain exchange is permitted by native LVS.
            nodes = [*sorted((nodes[0], nodes[2])), nodes[1], nodes[3]]
        rows.append((d['model'], tuple(nodes), float(d['params']['w']), float(d['params']['l'])))
    return ports, Counter(rows)


class PhysicalGateCapTopologyTests(unittest.TestCase):
    def test_physical_cell_matches_simulated_fine_topology_for_all_widths(self):
        self.assertEqual(physical.WIDTHS, prototype.WIDTHS)
        for profile in physical.WIDTHS:
            with self.subTest(profile=profile):
                self.assertEqual(signature(physical.schematic(profile), physical.name(profile)),
                                 signature(prototype.unit(old.schematic(), profile),
                                           prototype.name(profile)+'_unit'))


if __name__ == '__main__':
    unittest.main()
