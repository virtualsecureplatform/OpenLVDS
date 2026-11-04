# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phase_threshold_pair_v2 as original
import probe_phase_threshold_load_v2 as repair


class ThresholdLoadRepairTests(unittest.TestCase):
    def test_only_two_always_connected_native_base_capacitors_change(self):
        before,_=original.circuit();after=repair.circuit(before)
        for suffix in ['r','f']:
            after=after.replace(f'XCBASE{suffix} node_{suffix} VSS {original.CAP} w=4 l=4',
                                f'XCBASE{suffix} node_{suffix} VSS {original.CAP} w=2 l=2')
        self.assertEqual(after,before)
        with self.assertRaises(ValueError):repair.circuit(before.replace('XCBASEr','UNKNOWN'))
