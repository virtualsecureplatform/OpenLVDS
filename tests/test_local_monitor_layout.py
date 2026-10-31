# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from dll_design import candidate_source
from layout import circuits, flatten
from layout_dll_candidate import partition as split_dll
from layout_local_monitor import partition
from repair_dll_monitor import repaired_source

ROOT = Path(__file__).resolve().parents[1]


class LocalMonitorLayout(unittest.TestCase):
    def monitor(self):
        source = candidate_source((ROOT / 'analog/openlvds.spice').read_text(), 'ota_w8_c4',
                                  (ROOT / 'analog/experiments/phase_area.spice').read_text())
        ports, devices = flatten(circuits(repaired_source(source)), 'openlvds_dll_analog')
        _, quiet, _, public, _ = split_dll(devices, ports)
        return quiet, public

    def test_partition_preserves_devices_ports_and_local_analog_nodes(self):
        devices, ports = self.monitor()
        groups, public, shared = partition(devices, ports)
        self.assertEqual(Counter(d['name'] for d in devices),
                         Counter(d['name'] for g in groups.values() for d in g))
        self.assertTrue(set(ports) <= {p for pins in public.values() for p in pins})
        self.assertEqual(set(public['positive']) - {'VDDD', 'VSS'},
                         {'openlvds_dll_analog__PC', 'openlvds_dll_analog__XAREA__PA',
                          'openlvds_dll_analog__XAREA__PB', 'openlvds_dll_analog__XAREA__POS'})
        self.assertFalse(any('__XPOS__O' in n for n in shared))

    def test_cross_island_load_on_private_comparator_node_is_rejected(self):
        devices, ports = self.monitor()
        extra = deepcopy(next(d for d in devices if '__XPOS__' in d['name']))
        extra['name'] = 'openlvds_dll_analog__XAREA__XO_EXTRA'
        extra['nodes'][0] = 'openlvds_dll_analog__XAREA__XPOS__O'
        with self.assertRaisesRegex(ValueError, 'internal node escaped'):
            partition(devices + [extra], ports)
