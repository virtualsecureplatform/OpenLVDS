# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_recovery_driver_pcells_v338 as p


class BalancedPrimitiveInspection(unittest.TestCase):
    def text(self,s,gate='G',body='B',width=None,count=None):
        top=p.name(s)+'_flat';w=s['width_um'] if width is None else width;n=s['fingers'] if count is None else count
        return '.subckt '+top+' D G S B\n'+'\n'.join(f'X{i} D {gate} S {body} {s["model"]} w={w} l=.15 ad=.1 as=.1 pd=1 ps=1' for i in range(n))+'\n.ends\n'

    def test_actual_finger_count_and_per_finger_dimensions_are_checked(self):
        self.assertEqual({(s['kind'],s['fingers']) for s in p.PROFILES},{('n',16),('p',40)})
        for s in p.PROFILES:
            result=p.characterize(self.text(s),p.name(s),s);self.assertTrue(result['finger_count_and_dimensions_match']);self.assertTrue(result['all_gates_on_named_gate']);self.assertTrue(result['all_bodies_on_named_bulk']);self.assertFalse(result['qualified_phy'])
            self.assertFalse(p.characterize(self.text(s,width=s['width_um']/2),p.name(s),s)['finger_count_and_dimensions_match'])
            self.assertFalse(p.characterize(self.text(s,count=1),p.name(s),s)['finger_count_and_dimensions_match'])
            self.assertFalse(p.characterize(self.text(s,gate='G0'),p.name(s),s)['all_gates_on_named_gate'])

    def test_repeated_gate_and_separate_drain_source_accesses_are_preserved(self):
        text='rlabel metal1 0 0 0 0 0 G\nrlabel metal1 100 0 100 0 0 G\nrlabel metal1 20 40 20 40 0 D0\nrlabel metal1 60 40 60 40 0 S0\nrlabel locali -20 0 -20 0 0 B\n'
        accesses=p.terminal_accesses(text);self.assertEqual([a['name'] for a in accesses],['G','G','D0','S0','B']);self.assertEqual(accesses[1]['x_um'],.5)


if __name__=='__main__':unittest.main()
