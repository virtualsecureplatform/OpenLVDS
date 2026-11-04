# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_rc_drive_v2 as repair
import probe_dcdl_node_bank_pvt_v2 as original


class NativeDriveRepairTests(unittest.TestCase):
    def test_compound_gates_keep_identical_inputs_and_preserve_exact_rc_units(self):
        core,_=original.circuit(0,4);core=repair.parent_source.bank(core)
        for variant,(turns,merges) in repair.VARIANTS.items():
            changed=repair.circuit(core,variant)
            for name,count in [('Xt0',turns),('Xm0',merges)]:
                original_line=next(line for line in core.splitlines() if line.startswith(name+' '))
                for i in range(1,count):
                    self.assertIn(original_line.replace(name+' ',name+f'_parallel{i} ',1),changed)
            self.assertEqual(changed.count('openlvds_mim_switch_unit_v2'),31)
            self.assertIn('XCKICK r0 VSS sky130_fd_pr__cap_mim_m3_1 w=4 l=4',changed)
        with self.assertRaises(ValueError):repair.circuit(core,'unknown')
