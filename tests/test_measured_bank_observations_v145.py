# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measured_bank_observations_v145 as p
import test_regenerated_bank_observations_v60 as old_fixture


class MeasuredBankObservationTests(unittest.TestCase):
    def graph(self):
        cells=[]
        for level,copies in [(0,8),(1,2)]:
            for k in range(4):
                for j in range(copies):cells.append(dict(model=p.TG,pins=dict(EN=f'en{level}_{k}',ENB=f'en_b{level}_{k}')))
        cells += [dict(model=p.FINE,pins=dict(CTRL=f'fine{k}',CTRL_B=f'fine_b{k}')) for k in range(31)]
        return dict(cells=cells)

    def test_exact_typed_gate_coverage_counts_all_doubled_muxes_and_clear_switches(self):
        expected=p.expected_programming(self.graph())
        self.assertEqual(sum(expected.values()),173)
        self.assertEqual(expected['tg',p.NLVT,p.number('1.68'),'en0_2'],8)
        self.assertEqual(expected['tg',p.P,p.number('3.36'),'en_b1_3'],2)
        self.assertEqual(expected['fine',p.N,p.number('.42'),'fine_b17'],1)
        self.assertEqual(expected['fine',p.P,p.number('.84'),'fine_b17'],1)
        graph=self.graph();graph['cells'].pop()
        with self.assertRaisesRegex(ValueError,'40 balanced TG'):p.expected_programming(graph)

    def test_logical_short_and_missing_signal_alias_are_refused(self):
        plan,mag,g,ext,rc=old_fixture.RegeneratedControlMappingTests().fixture()
        with self.assertRaisesRegex(ValueError,'different logical nets'):p.aliases(mag,ext,rc,g,plan)
        with self.assertRaisesRegex(ValueError,'Missing native extraction alias'):p.aliases(mag,ext.replace('equiv "B" "gate_99.B"\n',''),rc,g,plan)

    def test_separated_rc_terminal_is_mapped_without_collapsing_the_observation(self):
        plan,mag,g,ext,_=old_fixture.RegeneratedControlMappingTests().fixture()
        rc='.subckt bank A B\nR1 gate_99.A.t0 A 12\nX1 B gate_99.A.t0 A A sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends bank\n'
        names,labelled,_,count=p.aliases(mag,ext,rc,g,plan)
        self.assertEqual(names,{'u_gate':'gate_99'});self.assertEqual(count,2)
        self.assertEqual(labelled['gate_99.A.t0'],'A');self.assertIn('gate_99.A.t0',rc)
        with self.assertRaisesRegex(ValueError,'public order'):p.aliases(mag,ext,rc.replace('bank A B','bank B A'),g,plan)


if __name__=='__main__':unittest.main()
