# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_design import candidate_source
from verify_candidate_rtl import check_assembly

ROOT=Path(__file__).resolve().parents[1]


class CandidateRTLAssembly(unittest.TestCase):
    def setUp(self):
        self.source=candidate_source((ROOT/'analog/openlvds.spice').read_text(),'ota_w8_c4',
            (ROOT/'analog/experiments/phase_area.spice').read_text())
        self.rtl=(ROOT/'rtl/experiments/openlvds_dll_core_area.v').read_text()

    def test_new_assembly_matches_characterized_spice_connections_and_public_ports(self):
        check_assembly(self.source,self.rtl)

    def test_legacy_qualifier_assembly_cannot_qualify_the_new_analog_macro(self):
        with self.assertRaisesRegex(ValueError,'differs from SPICE'):
            check_assembly(self.source,(ROOT/'rtl/openlvds_dll_core.v').read_text())

    def test_phase_and_reset_misconnections_are_rejected(self):
        for old,new in [('.FB(PH180)','.FB(PH90)'),('.RESET_N(RESET_N)','.RESET_N(PD_ENABLE)'),
                        ('.PD_REF(pd_ref)','.PD_REF(FB)')]:
            with self.assertRaisesRegex(ValueError,'differs from SPICE'):
                check_assembly(self.source,self.rtl.replace(old,new))

    def test_duplicate_terminal_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicated'):
            check_assembly(self.source,self.rtl.replace('.CLK(CLK)','.CLK(CLK),.CLK(CLK)'))
