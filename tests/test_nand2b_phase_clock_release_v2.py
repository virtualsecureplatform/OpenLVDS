# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import guarded_phase_clock_release_v4 as circuit


class Nand2bPhaseReleaseTests(unittest.TestCase):
    def inputs(self):
        library='.subckt sky130_fd_sc_hd__dfrtp_1 CLK D RESET_B VGND VNB VPB VPWR Q\nX0 Q RESET_B private VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        c=circuit.components
        rc={c.MODELS['nand2_8']:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])),
            c.MODELS['inv_8']:dict(info=dict(ports=['A','Y','VGND','VPWR'])),
            c.CLOCK_BUFFER:dict(info=dict(ports=['A','X','VGND','VPWR'])),
            circuit.NAND2B:dict(info=dict(ports=['A_N','B','Y','VPWR','VGND']))}
        return library,rc

    def test_only_arm_inverter_and_setter_are_replaced_by_native_inverting_input(self):
        library,rc=self.inputs();old=circuit.previous.source(library,rc,['private'],2)
        new=circuit.source(library,rc,['private'],2)
        retained=[line for line in old.splitlines()[1:-1] if not line.startswith(('Xarm_clock ','Xarm_set '))]
        for line in retained:self.assertIn(line,new.splitlines())
        self.assertNotIn('arm_clk_n',new)
        self.assertIn('Xarm_set CLK PREPARE arm_sn VPWR VGND '+circuit.NAND2B,new)
        self.assertEqual(new.count('XGUARD'),2)
        self.assertEqual(new.count('Xarm_set '),1)
        self.assertEqual(new.count('Xrequest_driver '),1)
        self.assertNotIn('.ic',new)

    def test_native_component_must_be_present_with_exact_pin_interface(self):
        library,rc=self.inputs();rc.pop(circuit.NAND2B)
        with self.assertRaisesRegex(ValueError,'Missing extracted'):circuit.source(library,rc,['private'],1)
        rc[circuit.NAND2B]=dict(info=dict(ports=['A','B','Y','VPWR','VGND']))
        with self.assertRaisesRegex(ValueError,'pin mismatch'):circuit.source(library,rc,['private'],1)


if __name__=='__main__':unittest.main()
