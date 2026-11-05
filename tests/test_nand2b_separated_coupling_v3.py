# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_nand2b_separated_coupling_v3 import network
from verify_nand2b_separated_output_v3 import same_source

MODEL='''.subckt pair A_N B Y VGND VPWR
R1 B wire_b 2
R2 Y wire_y 3
C1 wire_b wire_y 10f
C2 wire_y VPWR 2f
Xn wire_y wire_b VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15
.ends pair
'''


class SeparatedCouplingTests(unittest.TestCase):
    def test_distributed_nodes_are_counted_without_deleting_rc_or_intrinsic_devices(self):
        r=network(MODEL)
        self.assertAlmostEqual(r['port_coupling_ff']['B:Y'],10)
        self.assertAlmostEqual(r['port_coupling_ff']['VPWR:Y'],2)
        self.assertAlmostEqual(r['incident_explicit_parasitic_ff']['Y'],12)
        self.assertEqual(r['native_primitives'],{'sky130_fd_pr__nfet_01v8':1})
        renamed=MODEL.replace('wire_b','extracted_17').replace('wire_y','extracted_23')
        self.assertEqual(network(renamed),r)
        commented=MODEL.replace('wire_b 2','wire_b 2 $ width=0.3').replace('wire_y 10f','wire_y 10f $ extracted coupling').replace('w=1 l=.15','w=1 l=.15 $ native geometry')
        self.assertEqual(network(commented),r)

    def test_pin_shorts_nonpassivity_and_unknown_primitives_cannot_be_compared(self):
        for bad in [MODEL.replace('.ends pair','Rshort B Y 1\n.ends pair'),
                    MODEL.replace('10f','-10f'),MODEL.replace('wire_b 2','wire_b 0'),
                    MODEL.replace('sky130_fd_pr__nfet_01v8','unproven_device')]:
            with self.assertRaises(ValueError):network(bad)

    def test_source_proof_rejects_a_changed_guard_capacitor_or_transistor_size(self):
        old='.subckt old A Y\nXn Y A 0 0 native w=1 l=.15\nXcap Y 0 native_mim w=2 l=2\n.ends old\n'
        new=old.replace('old','new')
        same_source(old,new,'old','new')
        for bad in [new.replace('w=2','w=3'),new.replace('w=1','w=2')]:
            with self.assertRaises(ValueError):same_source(old,bad,'old','new')
