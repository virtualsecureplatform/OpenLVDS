# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_passive_rc_v2 import audit


class RcPassivityTests(unittest.TestCase):
    def test_negative_algebraic_vertex_is_a_direct_energy_witness(self):
        r=audit('.subckt gate A Y VGND\nR0 A n 10\nC0 n VGND -3.8f\nC1 Y VGND 10f\n.ends gate\n')
        self.assertFalse(r['elementwise_passive_passed']);self.assertTrue(r['negative_energy_witness'])
        vertices=r['rows'][0]['negative_diagonal_vertices'];self.assertEqual(len(vertices),1)
        self.assertEqual(vertices[0]['node'],'n');self.assertFalse(vertices[0]['device_terminal'])
        self.assertAlmostEqual(vertices[0]['diagonal_ff'],-3.8)

    def test_positive_coupled_rc_has_a_passivity_certificate(self):
        r=audit('.subckt cell A B VGND\nR0 A n 1\nC0 n B 2f\nC1 B VGND 3f\n.ends cell\n')
        self.assertTrue(r['elementwise_passive_passed']);self.assertFalse(r['negative_energy_witness'])

    def test_negative_edge_is_not_automatically_a_negative_diagonal_proof(self):
        r=audit('.subckt cell A B G\nC0 A B -1f\nC1 A G 3f\nC2 B G 3f\n.ends cell\n')
        self.assertFalse(r['elementwise_passive_passed']);self.assertFalse(r['negative_energy_witness'])


if __name__=='__main__':unittest.main()
