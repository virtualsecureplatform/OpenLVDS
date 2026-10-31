# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_pfd_capture import reset_views


class PFDCaptureDiagnostic(unittest.TestCase):
    def reference(self):
        return ('.subckt lvds_pfd DN FB PD_ENABLE REF RESET_N UP VGND VPWR\n'
                'Xdn_drive fb_ff/Q VGND VGND VPWR VPWR DN sky130_fd_sc_hd__buf_8\n'
                'Xup_drive ref_ff/Q VGND VGND VPWR VPWR UP sky130_fd_sc_hd__buf_8\n'
                'Xcoincidence UP DN VGND VGND VPWR VPWR clear/A_N sky130_fd_sc_hd__and2_4\n'
                'Xclear clear/A_N ena/X VGND VGND VPWR VPWR clear/X sky130_fd_sc_hd__and2b_4\n'
                '.ends\n')

    def test_reset_control_changes_only_the_two_coincidence_inputs(self):
        views = reset_views(self.reference())
        original = views['schematic_output_reset']
        changed = views['schematic_q_reset']
        self.assertEqual(changed, original.replace('Xcoincidence UP DN ',
                                                  'Xcoincidence ref_ff/Q fb_ff/Q '))
        self.assertIn('.subckt lvds_pfd_physical DN FB PD_ENABLE REF RESET_N UP VGND VPWR', changed)

    def test_missing_duplicate_or_already_changed_reset_is_rejected(self):
        source = self.reference()
        for altered in [source.replace('Xcoincidence UP DN ', 'Xcoincidence DN UP '),
                        source + 'Xcoincidence UP DN X sky130_fd_sc_hd__and2_4\n']:
            with self.assertRaisesRegex(ValueError, 'one output-tapped'):
                reset_views(altered)
