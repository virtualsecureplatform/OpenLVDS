# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import moscap_fine_bank_v75 as p


class InternalGateCapFineCellTests(unittest.TestCase):
    def fixture(self):
        return '''.subckt openlvds_mim_switch_2x3_v2 NODE EN ENB VDD VSS
X0 cap EN NODE VSS sky130_fd_pr__nfet_01v8 w=.42 l=.15 ad=.12 as=.12 pd=1.4 ps=1.4
X1 NODE ENB cap VDD sky130_fd_pr__pfet_01v8 w=.84 l=.15 ad=.24 as=.24 pd=2.2 ps=2.2
X2 cap ENB VSS VSS sky130_fd_pr__nfet_01v8 w=.42 l=.15 ad=.12 as=.12 pd=1.4 ps=1.4
X3 cap VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3
Xguard ENB VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=2
.ends openlvds_mim_switch_2x3_v2
'''

    def test_existing_switches_remain_and_capacitor_bodies_use_fixed_supplies(self):
        for profile,width in p.WIDTHS.items():
            text=p.unit(self.fixture(),profile);fine=p.name(profile)+'_unit'
            self.assertEqual(p.source.native.definitions(text)[fine][0],['NODE','EN','ENB','VDD','VSS'])
            for line in self.fixture().splitlines():
                if line.startswith(('X0 ','X1 ','X2 ')):self.assertIn(line,text)
            self.assertIn('Xgatecap_n VSS cap VSS VSS sky130_fd_pr__nfet_01v8 w='+width,text)
            self.assertIn('Xgatecap_p VDD cap VDD VDD sky130_fd_pr__pfet_01v8 w='+width,text)
            counts=p.source.primitive_counts(text,fine)
            self.assertEqual(sum(counts.values()),6);self.assertEqual(counts['sky130_fd_pr__cap_mim_m3_1'],1)
            self.assertIn('Xguard ENB VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=2',text)

    def test_unknown_quantum_and_changed_original_cell_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unknown'):p.unit(self.fixture(),'other')
        with self.assertRaisesRegex(ValueError,'interface'):p.unit(self.fixture().replace('NODE EN ENB VDD VSS','NODE ENB EN VDD VSS'),'w084')
        with self.assertRaisesRegex(ValueError,'MIM'):p.unit(self.fixture().replace('X3 cap VSS','X3 cap VDD'),'w084')


if __name__=='__main__':unittest.main()
