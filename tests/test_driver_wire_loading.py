# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_rc import collapse
from dll_campaign import text_block
from probe_driver_wire_loading import ideal_wire_core


class AuditedIdealWireControl(unittest.TestCase):
    NATIVE='''.subckt openlvds_driver_core D G VSS
R0 D dint 2
R1 VSS sint 1
C0 dint VSS 1e-15
X0 dint G sint VSS sky130_fd_pr__nfet_g5v0d10v5 w=5 l=1 ad=1.45 as=1.45 pd=10.58 ps=10.58
XCAP D VSS sky130_fd_pr__cap_mim_m3_1 w=29 l=29
XRES D G VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=60
.ends openlvds_driver_core
.subckt lvds_bias IREF NB VA VS
RBIAS IREF NB 10
.ends lvds_bias
'''
    def test_geometry_and_intentional_devices_remain_while_wire_rc_is_removed(self):
        collapsed=collapse(text_block(self.NATIVE,'openlvds_driver_core'))
        control=ideal_wire_core(self.NATIVE,collapsed)
        core=text_block(control,'openlvds_driver_core')
        self.assertNotRegex(core,r'(?m)^[RC]0\b')
        self.assertIn('ad=1.45 as=1.45 pd=10.58 ps=10.58',core)
        self.assertIn('XCAP',core);self.assertIn('XRES',core)
        self.assertEqual(text_block(control,'lvds_bias'),text_block(self.NATIVE,'lvds_bias'))

    def test_modified_or_missing_pdk_device_is_not_a_wire_only_control(self):
        collapsed=collapse(text_block(self.NATIVE,'openlvds_driver_core'))
        with self.assertRaises(ValueError):ideal_wire_core(self.NATIVE,collapsed.replace('ad=1.45','ad=0'))
        with self.assertRaises(ValueError):ideal_wire_core(self.NATIVE,'\n'.join(l for l in collapsed.splitlines() if not l.startswith('XRES')))
