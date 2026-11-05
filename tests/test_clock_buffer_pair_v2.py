# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_clock_buffer_pair_v2 as pair
from dcdl_bank_native_reference_v2 import definitions,expand


class ClockPairNativeTopologyTests(unittest.TestCase):
    def source(self):
        return '.subckt '+pair.CHILD+' A X VPWR VGND\nXn X private A VGND sky130_fd_pr__nfet_01v8 w=1.68 l=.15\n.ends '+pair.CHILD+'\n'

    def test_duplicate_native_cells_share_only_public_ports_and_retain_private_nodes_and_dimensions(self):
        text=pair.schematic(self.source());self.assertTrue(text.startswith(self.source()))
        leaves=expand(definitions(text),pair.NAME,{p:p for p in pair.PORTS},'top')
        self.assertEqual(len(leaves),2)
        self.assertEqual(len({d[1][1] for d in leaves}),2)
        for _,nodes,model,params in leaves:
            self.assertEqual([nodes[i] for i in [0,2,3]],['X','A','VGND'])
            self.assertEqual(model,'sky130_fd_pr__nfet_01v8');self.assertEqual(params,{'w':'1.68','l':'.15'})

    def test_missing_or_duplicated_child_formals_cannot_be_wired_as_a_clock_pair(self):
        for bad in [self.source().replace('A X VPWR VGND','A X VPWR'),self.source().replace('A X VPWR VGND','A X VPWR VGND A')]:
            with self.assertRaises(ValueError):pair.schematic(bad)


if __name__=='__main__':unittest.main()
