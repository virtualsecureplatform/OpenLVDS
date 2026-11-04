# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_fine_repair_v2 as repair
import layout


class FineTransmissionGateRepairTests(unittest.TestCase):
    def test_only_two_transmission_gate_widths_change(self):
        old=repair.previous.schematic(4).splitlines();new=repair.schematic().splitlines()
        self.assertEqual(len(old),len(new));changed=[]
        for a,b in zip(old,new):
            if a==b:continue
            x,y=a.split(),b.split();changed.append(x[0])
            self.assertEqual([w for w in x if not w.startswith('w=')],[w for w in y if not w.startswith('w=')])
            self.assertEqual(float(next(w[2:] for w in y if w.startswith('w='))),2*float(next(w[2:] for w in x if w.startswith('w='))))
        self.assertEqual(changed,['XSWN','XSWP'])

    def test_native_topology_capacitor_weights_and_clear_device_are_preserved(self):
        po,old=layout.flatten(layout.circuits(repair.previous.schematic(4)),repair.NAME)
        pn,new=layout.flatten(layout.circuits(repair.schematic()),repair.NAME)
        self.assertEqual(po,pn);self.assertEqual(pn,repair.PORTS);self.assertEqual(len(new),5)
        self.assertEqual(old[2:],new[2:])
        for a,b in zip(old[:2],new[:2]):
            self.assertEqual(a['nodes'],b['nodes']);self.assertEqual(a['model'],b['model'])
