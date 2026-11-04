# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout
import mim_switch_unit_v2 as original
import mim_switch_2x3_v2 as larger
import mim_switch_2x3_layout_v2 as routing


class LargerFineUnitTests(unittest.TestCase):
    def test_only_fine_mim_area_changes_and_model_name_is_distinct(self):
        self.assertNotEqual(larger.NAME,original.NAME)
        expected=original.schematic().replace(original.NAME,larger.NAME).replace('XCUNIT CAP VSS '+larger.CAP+' w=2 l=2',
            'XCUNIT CAP VSS '+larger.CAP+' w=2 l=3')
        self.assertEqual(larger.schematic(),expected)
        ports,devices=layout.flatten(layout.circuits(larger.schematic()),larger.NAME)
        self.assertEqual(ports,['NODE','EN','ENB','VDD','VSS']);self.assertEqual(len(devices),5)
        self.assertEqual(devices[3]['params'],dict(w='2',l='3'))
        self.assertEqual(devices[4]['params'],dict(w='2',l='2'))

    def test_routing_uses_new_geometry_and_restores_original_module_even_on_failure(self):
        previous=routing.routing.unit
        def check(*args):
            self.assertIs(routing.routing.unit,larger)
            raise ValueError('deliberate geometry rejection')
        with patch.object(routing.routing,'draw',side_effect=check):
            with self.assertRaisesRegex(ValueError,'geometry rejection'):routing.draw(None,None,None)
        self.assertIs(routing.routing.unit,previous)

    def test_plan_routes_larger_cap_beyond_actual_native_primitive_extent(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'constraints/v2/mim_switch_2x3_legal.json').read_text())
        # Fixed geometry from the native 2x3 PCell: +/-2.08 by +/-1.70 um.
        self.assertGreater(plan['cap_escape_y']-plan['cap_centers'][0][1]-1.7,1.34)
        self.assertGreater(plan['buses']['CAP']-plan['cap_escape_y'],.5)
        self.assertEqual(len(plan['bottom_via_x']),2)
