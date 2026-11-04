# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout
import mim_switch_unit_v2 as unit
import dcdl_cap_strong_v2 as native


class FineUnitTopologyTests(unittest.TestCase):
    def test_physical_unit_matches_the_actual_native_fine_switch_and_control_shunt(self):
        ports,devices=layout.flatten(layout.circuits(unit.schematic()),unit.NAME)
        self.assertEqual(ports,['NODE','EN','ENB','VDD','VSS']);self.assertEqual(len(devices),5)
        _,source=native.circuit(0)
        aliases={'r0':'NODE','E0':'EN','EB0':'ENB','cap0':'CAP','VDD':'VDD','VSS':'VSS'}
        for physical,expected in zip(devices[:3],source[:3]):
            self.assertEqual(physical['model'],expected['model'])
            self.assertEqual(float(physical['params']['w']),expected['width_um'])
            self.assertEqual(float(physical['params']['l']),expected['length_um'])
            self.assertEqual([n.replace(unit.NAME+'__','') for n in physical['nodes']],
                             [aliases[n] for n in expected['terminals']])
        for d,expected_node in zip(devices[3:],['CAP','ENB']):
            self.assertEqual(d['model'],unit.CAP)
            self.assertEqual([n.replace(unit.NAME+'__','') for n in d['nodes']],[expected_node,'VSS'])
            self.assertEqual(d['params'],dict(w='2',l='2'))
