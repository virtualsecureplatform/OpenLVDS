# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_nand_node_shunt_v2 as circuit
import test_dcc_nand_mid_shunt_v2 as fixture


class StaticGateOutputShuntTests(unittest.TestCase):
    def test_one_real_output_mim_per_logical_net_including_reset_output(self):
        library=fixture.StaticGateShuntTests().library();text,nodes=circuit.source(1,library)
        self.assertEqual(len(nodes['stack_nodes']),27);self.assertEqual(len(nodes['output_nodes']),27)
        self.assertEqual(len(circuit.devices(text)),31)
        self.assertEqual(text.count('XOUTCAP'),27)
        for node in ['xor_n','xor_a','xor_b','xor_out','clock_out']:
            matches=[line for line in text.splitlines() if line.startswith('XOUTCAP') and line.split()[1]==node]
            self.assertEqual(len(matches),1,node)
            self.assertTrue(matches[0].endswith('VGND '+circuit.CAP+' w=2 l=2'))
        self.assertFalse(set(nodes['output_nodes'])&{'phase0','phase180','reset_n','VPWR','VGND'})
        original=circuit.unshunted.source(1,library)
        retained='\n'.join(line for line in text.splitlines() if not line.startswith(('XSTACKCAP','XOUTCAP')))+'\n'
        self.assertEqual(retained.replace(circuit.NAME,circuit.unshunted.NAME),original)


if __name__=='__main__':unittest.main()
