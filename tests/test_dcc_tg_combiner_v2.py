# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_tg_combiner_v2 as circuit
import probe_dcc_tg_combiner_v2 as pilot


class RealTgDccTests(unittest.TestCase):
    def library(self):
        result=''
        for model,ports,nodes in [('nand2_2','A B VGND VNB VPB VPWR Y','Y A internal VGND'),
                                  ('nand2_8','A B VGND VNB VPB VPWR Y','Y B internal VGND'),
                                  ('inv_1','A VGND VNB VPB VPWR Y','Y A VGND VGND')]:
            result+=f'.subckt sky130_fd_sc_hd__{model} {ports}\nX0 {nodes} sky130_fd_pr__nfet_01v8 w=.64 l=.15\n.ends\n'
        return result

    def test_both_real_tg_muxes_compute_xor_from_complementary_storage(self):
        for a in [0,1]:
            for b in [0,1]:
                values=dict(a=a,a_qb=1-a,b=b,b_qb=1-b);on=[]
                for _,data,en,enb in circuit.switches():
                    self.assertEqual(values[enb],1-values[en])
                    if values[en]:on.append(values[data])
                self.assertEqual(on,[a^b,a^b])

    def test_physical_devices_and_only_the_final_stack_have_the_larger_mim(self):
        text,nodes=circuit.source('tg1',self.library());mos=circuit.devices(text)
        tg=[d for d in mos if d['name'].startswith('Xtg_')]
        self.assertEqual(len(tg),8);self.assertEqual(sum(d['model']==circuit.N for d in tg),4)
        self.assertTrue(all(d['nodes'][3]==('VGND' if d['model']==circuit.N else 'VPWR') for d in tg))
        caps=[l for l in text.splitlines() if l.startswith('XSTACKCAP')]
        self.assertEqual(sum('w=4 l=4' in l for l in caps),1)
        self.assertTrue(all('output_reset__' in l for l in caps if 'w=4 l=4' in l))
        self.assertIn('xor_out',nodes['output_nodes']);self.assertEqual(len(nodes['output_nodes']),24)
        self.assertNotIn('Xxor_n_',text);self.assertNotIn('.ic',text)
        with self.assertRaisesRegex(ValueError,'Undeclared'):circuit.source('ideal',self.library())

    def test_a_good_mean_cannot_hide_a_bad_individual_half_cycle(self):
        for error,expected in [(150,False),(49,True),(None,False)]:
            report=dict(pilot_passed=True,maximum_individual_half_cycle_error_ps=error)
            with patch.object(pilot,'measure',return_value=report),patch.object(circuit,'devices',return_value=[]):
                result=pilot.assess(Path('/fixture'),{},'')
            self.assertTrue(result['mean_screen_passed']);self.assertEqual(result['pilot_passed'],expected)


if __name__=='__main__':unittest.main()
