# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_pfd_physical_candidate import library
from dll_campaign import text_block


class PFDPhysicalProbe(unittest.TestCase):
    def reference(self):
        return ('.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\n'
                'XOLD UP DN REF FB RESET_N PD_ENABLE VDDD VSS lvds_pfd_physical\n.ends lvds_pfd\n'
                '.subckt lvds_pfd_physical UP DN REF FB RESET_N PD_ENABLE VDDD VSS\n'
                'COLD UP VSS 9f\n.ends lvds_pfd_physical\n'
                '.subckt unchanged A B\nRKEEP A B 10\n.ends unchanged\n')

    def physical(self):
        return ('.subckt lvds_pfd DN FB PD_ENABLE REF RESET_N UP VGND VPWR\n'
                'CNEW DN VGND 3f\n.ends lvds_pfd\n')

    def test_adapter_uses_actual_extracted_pin_order_and_preserves_other_blocks(self):
        ports = 'DN FB PD_ENABLE REF RESET_N UP VGND VPWR'.split()
        result = library(self.reference(), self.physical(), ports)
        self.assertIn('XPHYS DN FB PD_ENABLE REF RESET_N UP VSS VDDD lvds_pfd_physical', result)
        self.assertIn('CNEW DN VGND 3f', result)
        self.assertNotIn('COLD', result)
        self.assertEqual(text_block(result, 'unchanged'), text_block(self.reference(), 'unchanged'))
        self.assertIn('.ends lvds_pfd_physical', result)

    def test_extra_missing_and_duplicate_formal_ports_are_rejected(self):
        ports = 'DN FB PD_ENABLE REF RESET_N UP VGND VPWR'.split()
        for altered in [ports + ['ERR'], ports[:-1], ports[:-1] + ['VGND']]:
            with self.assertRaisesRegex(ValueError, 'ports differ'):
                library(self.reference(), self.physical(), altered)

    def test_wrong_top_name_cannot_silently_reuse_old_native_pfd(self):
        with self.assertRaisesRegex(ValueError, 'physical PFD header'):
            library(self.reference(), self.physical().replace('lvds_pfd', 'unexpected'),
                    'DN FB PD_ENABLE REF RESET_N UP VGND VPWR'.split())
