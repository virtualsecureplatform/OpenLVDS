# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import static_phase_clock_release_v6 as circuit
import probe_static_phase_clock_release_v6 as pilot
import verify_static_phase_clock_release_v6 as verifier


class RoutedPairStaticReleaseTests(unittest.TestCase):
    def test_routed_pair_replaces_only_three_shared_low_setters(self):
        c=circuit.components
        rc={c.MODELS['nand2_'+str(n)]:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])) for n in [4,8]}
        rc[c.CLOCK_BUFFER]=dict(info=dict(ports=['A','X','VGND','VPWR']))
        for name in [circuit.previous.previous.NAND2B,*circuit.previous.MACROS.values(),circuit.PAIR]:
            rc[name]=dict(info=dict(ports=['A_N','B','Y','VGND','VPWR']))
        old=circuit.previous.source(rc,'o1').splitlines()[1:-1];new=circuit.source(rc,'pair').splitlines()[1:-1]
        unchanged=[r for r in old if r.split()[-1]!=circuit.previous.MACROS['o1']]
        self.assertTrue(all(r in new for r in unchanged));self.assertEqual(len(new),len(old)-3)
        expected=[('low0','request_i'),('low1','high1'),('low2','PREPARE')]
        for tag,prior in expected:self.assertIn(f'X{tag}_set_pair CLK {prior} {tag}_sn VGND VPWR '+circuit.PAIR,new)
        self.assertFalse(any(circuit.previous.MACROS['o1'] in r for r in new))
        self.assertEqual({s['duty'] for s in pilot.specifications()},{.4,.6})
        self.assertEqual({s['stop_level'] for s in pilot.specifications()},{0,1})

    def test_complete_profile_requires_four_positive_measured_cases(self):
        good=dict(counter_feasibility_passed=True,terminal_stress=[dict(max_terminal_difference_v=1.9)],margin_to_next_half_phase_ps=dict(prepare=400,public_release=600))
        rows=[dict(task=dict(spec=s),result=good,error=None) for s in pilot.specifications()]
        self.assertTrue(verifier.assess(rows)[0]['source_counter_feasibility_passed'])
        with self.assertRaises(ValueError):verifier.assess(rows[:-1])
        rows[0]=dict(rows[0],result=None,error='Phase event count')
        self.assertFalse(verifier.assess(rows)[0]['source_counter_feasibility_passed'])


if __name__=='__main__':unittest.main()
