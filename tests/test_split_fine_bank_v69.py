# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import split_fine_bank_v69 as p


class SplitFineArchitectureTests(unittest.TestCase):
    def fixture(self):
        rows=['.subckt '+p.FINE+' NODE EN ENB VDD VSS',
              'XN NODE EN cap VSS sky130_fd_pr__nfet_01v8 w=.42 l=.15',
              'XP NODE ENB cap VDD sky130_fd_pr__pfet_01v8 w=.84 l=.15',
              'XC cap VSS sky130_fd_pr__cap_mim_m3_1 w=2 l=3','.ends '+p.FINE,
              '.subckt '+p.source.NAME+' IN OUT selected VPWR VGND']
        rows += [f'Xfine_unit{k} OUT fine{k} fine_b{k} VPWR VGND '+p.FINE for k in range(31)]
        return '\n'.join(rows+['.ends '+p.source.NAME,''])

    def test_only_last_twelve_fine_signal_connections_change(self):
        text=self.fixture();new=p.transform(text)
        for k in range(31):
            node='selected' if k in p.MOVED else 'OUT'
            self.assertIn(f'Xfine_unit{k} {node} fine{k} fine_b{k} VPWR VGND '+p.FINE,new)
        self.assertEqual(p.source.primitive_counts(text,p.source.NAME),p.source.primitive_counts(new,p.NAME))

    def test_baseline_is_identical_except_top_name(self):
        text=self.fixture();self.assertEqual(p.transform(text,moved=()),text.replace(p.source.NAME,p.NAME))

    def test_changed_original_loading_missing_unit_or_interface_is_rejected(self):
        text=self.fixture()
        for bad in (text.replace('Xfine_unit20 OUT','Xfine_unit20 IN'),
                    text.replace('Xfine_unit30','Xother'),text.replace('NODE EN ENB VDD VSS','NODE ENB EN VDD VSS')):
            with self.assertRaises(ValueError):p.transform(bad)
        with self.assertRaises(ValueError):p.transform(text,moved=(1,2))


if __name__=='__main__':unittest.main()
