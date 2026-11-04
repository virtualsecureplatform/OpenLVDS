# SPDX-License-Identifier: GPL-3.0-only
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_weighted_direct_v2 as circuit
import probe_weighted_direct_v2 as pilot
import verify_weighted_direct_v2 as verifier


class WeightedDirectTests(unittest.TestCase):
    def test_guards_preserve_every_coarse_connection_and_direct_ports(self):
        plain={c['name']:c for c in circuit.core_instances('plain')}
        guarded={c['name']:c for c in circuit.core_instances('guarded')}
        paired=circuit.direct.COMPOUNDS[circuit.direct.native.SC+'nand2b_4'];replacements=0
        for name,cell in plain.items():
            if cell['model']==paired:
                for i in range(2):
                    replacement=guarded.pop(name+'_guard'+str(i))
                    self.assertEqual(replacement['model'],circuit.GUARD)
                    self.assertEqual(replacement['pins'],cell['pins'])
                replacements+=1
            else:self.assertEqual(guarded.pop(name),cell)
        self.assertFalse(guarded);self.assertEqual(replacements,31)
        self.assertNotIn('input_buffer',plain);self.assertNotIn('output_buffer',plain)
        self.assertEqual(plain['forward0']['pins']['A'],'IN');self.assertEqual(plain['merge0']['pins']['Y'],'OUT')
        self.assertEqual(sum(n.startswith('forward') for n in plain),15)

    def test_fixture_exercises_carry_and_repeated_code_with_no_dangling_r0_probe(self):
        spec=pilot.specifications()[0]
        with patch.dict(os.environ,PDK_ROOT='/pdk'):text=pilot.fixture(Path('/fixture'),spec,[])
        self.assertIn('.tran 2p 60n 0 2p',text);self.assertIn('.options itl4=100',text)
        self.assertNotIn('V(XD:r0)',text);self.assertIn(' '+circuit.NAME+'\n',text)
        self.assertEqual(spec['codes'],[0,1,15,16,31,0])

    def test_native_tie_resistors_are_retained_and_private_mos_nodes_stay_distinct(self):
        body='.subckt '+circuit.NAME+' '+' '.join(circuit.PORTS)+'\nX0 OUT IN private VSS '+circuit.weighted.N+' w=.42 l=.15\nXR0 VSS OUT sky130_fd_pr__res_generic_po w=.48 l=.5\n.ends\n'
        ds=circuit.devices(body)
        self.assertEqual(ds[0]['terminals'],['OUT','IN','XD:private','0'])
        self.assertEqual(len(ds),1)
        self.assertIn('XR0 VSS OUT sky130_fd_pr__res_generic_po',body)
        for changed in [body.replace('res_generic_po','unknown_leaf'),body.replace('XR0 VSS OUT','XR0 VSS OUT IN')]:
            with self.assertRaises(ValueError):circuit.devices(changed)

    def rows(self):
        return [dict(task=dict(spec=spec),result=dict(samples=[dict(code=c,rise_delay_ps=300+spec['coarse']*200+10*c,
              fall_delay_ps=300+spec['coarse']*200+10*c) for c in spec['codes']],terminal_screen_passed=True,minimum_quarter_headroom_ps=300)) for spec in pilot.specifications()]

    def test_overlap_carry_monotonicity_stress_and_coverage_are_required(self):
        self.assertTrue(all(g['sparse_feasibility_passed'] for g in verifier.assess(self.rows())))
        with self.assertRaises(ValueError):verifier.assess(self.rows()[:-1])
        rows=self.rows();rows[0]['result']['samples'].pop(2)
        with self.assertRaisesRegex(ValueError,'carry/repeat'):verifier.assess(rows)
        for index,value in [(3,449),(3,481),(4,400)]:
            rows=self.rows();rows[0]['result']['samples'][index]['fall_delay_ps']=value
            self.assertFalse(verifier.assess(rows)[0]['sparse_feasibility_passed'])
        for key,value in [('terminal_screen_passed',False),('minimum_quarter_headroom_ps',-1)]:
            rows=self.rows();rows[0]['result'][key]=value
            self.assertFalse(verifier.assess(rows)[0]['sparse_feasibility_passed'])


if __name__=='__main__':unittest.main()
