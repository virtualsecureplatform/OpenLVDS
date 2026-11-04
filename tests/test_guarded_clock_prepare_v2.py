# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import guarded_clock_prepare_v2 as prepare


class GuardedClockPrepareTests(unittest.TestCase):
    def test_guards_attach_only_to_existing_private_nodes_in_all_three_native_ffs(self):
        library='.subckt sky130_fd_sc_hd__dfrtp_1 CLK D RESET_B VGND VNB VPB VPWR Q\nX0 Q CLK private VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        rc={prepare.components.CLOCK_BUFFER:dict(info=dict(ports=['A','X','VGND','VPWR']))}
        text=prepare.source(library,rc,['private'],1)
        self.assertEqual(text.count('XGUARD'),3);self.assertEqual(text.count('w=.65 l=.15'),3)
        for tag in ['r0','r1','r2']:self.assertIn(tag+'__private VGND '+prepare.CAP,text)
        with self.assertRaisesRegex(ValueError,'actual native'):prepare.source(library,rc,['missing'],1)
        self.assertNotIn('.ic',text)

    def test_only_internal_data_qualification_moves_to_prepare(self):
        before=prepare.components.strengthen([c for c in prepare.components.dcc.storage.gates(2) if not c[0].startswith('xor_')])
        after={tag:(model,pins) for tag,model,pins in prepare.dcc_gates()}
        for tag,model,pins in before:
            expected=dict(pins)
            if tag in ['a_data_n','b_data_n']:expected['A']='prepare_n'
            self.assertEqual(after[tag],(model,expected))
        self.assertEqual(after['output_reset'][1]['A'],'reset_n')
        self.assertEqual(prepare.gates()[1][2]['Q'],'PREPARE')
        self.assertEqual(prepare.gates()[2][2]['D'],'PREPARE')
        self.assertTrue(all(p['RESET_B']=='REQUEST' for _,_,p in prepare.gates()))


if __name__=='__main__':unittest.main()
