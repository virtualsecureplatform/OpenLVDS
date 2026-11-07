# SPDX-License-Identifier: GPL-3.0-only
"""Guard actual whole-counter geometry before shared-wire RC extraction."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
try:
    import qualify_shunted_counter_rc_v350 as p
except ModuleNotFoundError as error:
    if error.name not in ('klayout','numpy'):raise
    p=None


@unittest.skipIf(p is None,'requires project counter-physical Python with NumPy and KLayout')
class ShuntedCounterRcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'build/diagnostics/shunted_counter_physical_v349/2090d79ff6a2bad2'
        cls.state=json.loads((cls.folder/'state.json').read_text())
        cls.report=json.loads((cls.folder/'summary.json').read_text())
        cls.text=(cls.folder/p.NAME/(p.NAME+'.lvs.spice')).read_text()

    def test_actual_passed_counter_and_native_census(self):
        p.require_physical(self.state,self.report)
        census=p.census(self.text)
        self.assertEqual(census['native_model_counts'],p.EXPECTED)
        self.assertEqual(census['native_primitives'],795)
        self.assertEqual(census['ports'],p.PORTS)

    def test_failed_incomplete_or_shortened_physical_proof_is_rejected(self):
        for state in (dict(self.state,status='routing'),dict(self.state,passed=False)):
            with self.assertRaises(ValueError):p.require_physical(state,self.report)
        for key,value in (('drc_count','18'),('lvs_passed',False),('native_macro_roles',22),('native_mim',50)):
            report=deepcopy(self.report);report['physical'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.require_physical(self.state,report)

    def test_missing_mask_junction_or_placement_proof_is_rejected(self):
        for group,key in (('native_master_witness','integrated_macro_placements_verified'),
                          ('native_master_witness','all_native_masks_and_electrical_labels_preserved'),
                          ('native_parameters','all_reference_supplied_junctions_preserved')):
            report=deepcopy(self.report);report['physical'][group][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):p.require_physical(self.state,report)

    def test_changed_native_primitive_model_or_public_ports_is_rejected(self):
        with self.assertRaises(ValueError):
            p.census(self.text.replace('sky130_fd_pr__pfet_01v8_hvt','sky130_fd_pr__pfet_01v8',1))
        with self.assertRaises(ValueError):
            p.census(self.text.replace('.subckt '+p.NAME+'_flat RCLK ','.subckt '+p.NAME+'_flat WRONG ',1))


if __name__=='__main__':unittest.main()
