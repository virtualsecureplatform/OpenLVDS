# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import expand_analog_arbiter_v2 as expansion


class AnalogArbiterPVTTests(unittest.TestCase):
    def test_every_pvt_has_both_signs_swaps_and_three_slew_pairs(self):
        req=json.loads((expansion.ROOT/'requirements.json').read_text())
        specs=expansion.specifications(req)
        self.assertEqual(len(specs),180)
        keys={(s['process'],s['temperature'],s['swap'],s['offset_ps'],
               s['reference_slew_ps'],s['feedback_slew_ps']) for s in specs}
        self.assertEqual(len(keys),180)
        for process in req['process_corners']:
            for temperature in req['temperatures_c']:
                self.assertEqual(sum(s['process']==process and s['temperature']==temperature for s in specs),12)

    def test_deck_selects_requested_native_corner_temperature_and_keeps_supplies(self):
        spec=dict(process='sf',temperature=0,drive=1,swap=1,offset_ps=-20,
                  reference_slew_ps=20,feedback_slew_ps=200)
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            text=expansion.fixture(Path('/context'),spec,[])
        self.assertIn('" sf\n',text)
        self.assertIn('.options device temp=0\n',text)
        self.assertIn('VDD VDD 0 1.8\nVDDIO VDDIO 0 3.3\n',text)
        self.assertIn('VSW SW 0 1.8\n',text)
        self.assertNotIn('" ss\n',text)

    def test_changed_parent_fixture_is_rejected(self):
        with patch.object(expansion.pilot.original,'fixture',return_value='unknown'):
            with self.assertRaisesRegex(ValueError,'PVT declaration'):
                expansion.fixture(Path('/context'),{},[])
