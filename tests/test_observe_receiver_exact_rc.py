# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import observe_receiver_exact_rc as observation


class ExactReceiverProbeRetention(unittest.TestCase):
    source='''.subckt openlvds_receiver_core A B VSS
R0 A PROBE 10
R1 PROBE INTERIOR 20
R2 INTERIOR B 30
C0 B VSS 1f
X0 A B VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=.15
.ends openlvds_receiver_core
'''
    def test_probe_only_vertex_survives_while_unobserved_algebraic_vertex_is_eliminated(self):
        before,after,text,count,nodes=observation.reduced(self.source,['.print tran V(XRC:PROBE)\n'],8)
        self.assertEqual(nodes,{'PROBE'});self.assertEqual(count,1)
        self.assertIn('PROBE',after['graph']);self.assertNotIn('INTERIOR',after['graph'])
        self.assertEqual(observation.static_signature(before),observation.static_signature(after))
        proof=observation.witness(before,after)
        self.assertTrue(proof['passed']);self.assertEqual(proof['witnesses'],4)

    def test_missing_or_ambiguous_probes_cannot_be_ignored(self):
        for deck in ['.print tran V(XRC:MISSING)\n','.print tran V(OUTPUT)\n','.print tran V(XRC:PROBE)\n.print tran V(XRC:A)\n']:
            with self.assertRaises(ValueError):observation.reduced(self.source,[deck],8)

    def test_all_capacitor_and_device_terminal_statements_are_retained(self):
        before,after,text,count,nodes=observation.reduced(self.source,['.print tran V(XRC:a) V(XRC:b)\n'],8)
        self.assertEqual(nodes,{'A','B'})
        self.assertIn('C0 B VSS 1f',text)
        self.assertIn('X0 A B VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=.15',text)
        with self.assertRaises(ValueError):observation.reduced(self.source,['.print tran V(XRC:A)\n'],99)
