# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_driver_complete_native_pilot import analog_targets


class LogicalAnalogObservationTargets(unittest.TestCase):
    SOURCE='''.subckt openlvds_driver_core OUTP VREF NB VDDIO VSS
XRCP OUTP CM VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=10.25
XRCM0 CM CMS VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=60
XCMNP XCM__L CM XCM__T VSS sky130_fd_pr__nfet_g5v0d10v5 w=8 l=1
.ends openlvds_driver_core
'''
    def source(self):
        return '''.subckt amp PLUS MINUS OUT NB VA VS
XNP L PLUS T VS sky130_fd_pr__nfet_g5v0d10v5 w=8 l=1
XNT T NB VS VS sky130_fd_pr__nfet_g5v0d10v5 w=2 l=1
.ends amp
.subckt openlvds_driver_core OUTP VREF NB VDDIO VSS
XRCP OUTP CM VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=10.25
XRCM0 CM CMS VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=60
XCM CM VREF SINK NB VDDIO VSS amp
.ends openlvds_driver_core
'''

    def placements(self):
        return [dict(instance=i,members=['openlvds_driver_core'+n]) for i,n in
            [('I91','__XRCP'),('I63','__XRCM0'),('I44','__XCM__XNP_F0'),('I17','__XCM__XNT_F0')]]

    def test_source_nets_determine_physical_pins_after_arbitrary_placement_order(self):
        targets=analog_targets(self.source(),self.placements())
        self.assertEqual(targets['CM']['physical_pin'],'I91.R2')
        self.assertEqual(targets['CMS']['physical_pin'],'I63.R2')
        self.assertEqual(targets['CMFB_L']['physical_pin'],'I44.D')
        self.assertEqual(targets['CMFB_T']['physical_pin'],'I17.D')

    def test_wrong_source_connection_or_ambiguous_membership_rejected(self):
        with self.assertRaises(ValueError):analog_targets(self.source().replace('XRCP OUTP CM','XRCP OUTP WRONG'),self.placements())
        with self.assertRaises(ValueError):analog_targets(self.source(),self.placements()+[self.placements()[0]])
