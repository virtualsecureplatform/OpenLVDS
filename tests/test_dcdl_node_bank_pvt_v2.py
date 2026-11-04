# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_node_bank_pvt_v2 as source


class NodeBankPVTTests(unittest.TestCase):
    def test_every_coarse_and_pvt_has_dense_codes_and_bulk_stress(self):
        req=json.loads((source.ROOT/'requirements.json').read_text());specs=source.specifications(req,4)
        self.assertEqual(len(specs),150)
        for p in req['process_corners']:
            for t in req['temperatures_c']:
                for c in [0,1]:
                    group=[s for s in specs if (s['process'],s['temperature'],s['coarse'])==(p,t,c)]
                    dense=[code for s in group if s['pattern'].startswith('dense') for code in s['codes']]
                    self.assertEqual(dense,list(range(32)))
                    self.assertEqual([s['codes'] for s in group if s['pattern']=='bulk'],[source.pilot.parent_source.CODES])

    def test_exact_native_geometry_and_complementary_shunts_remain_in_fixture(self):
        for geometry in [2,4]:
            for c in [0,1]:
                text,devices=source.circuit(c,geometry)
                self.assertIn(f'XCKICK r0 VSS sky130_fd_pr__cap_mim_m3_1 w={geometry} l={geometry}',text)
                self.assertEqual(len(devices),93)
            spec=dict(process='fs',temperature=25,coarse=1,codes=source.pilot.parent_source.CODES,
                      restore='mim2x2',control_slew_ps=20,node_geometry_um=geometry)
            with patch.dict(os.environ,PDK_ROOT='/pdk'):
                deck=source.fixture(Path('/context'),spec)
            self.assertIn('" fs\n',deck);self.assertIn('temp=25\n',deck)
            self.assertIn('/coarse1.spice"',deck)
            self.assertEqual(deck.count('XCEB'),31)
            self.assertIn('VDD VDD 0 1.8',deck)
            self.assertIn('9.99n 0 10.01n 1.8',deck)
