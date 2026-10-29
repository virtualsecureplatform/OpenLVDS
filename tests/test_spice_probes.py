# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from spice_probes import ProbeNetwork
from dll_candidate_library import observation_nodes


class SPICEProbes(unittest.TestCase):
    def test_hierarchical_probe_must_reach_an_existing_node(self):
        library = '''.subckt leaf A Y
+ SUPPLY
XC control.t9 0 sky130_fd_pr__cap_mim_m3_1 l=30 w=30
XR A control.t9 sky130_fd_pr__res_high_po_0p35 l=1
.ends leaf
.subckt parent A Y SUPPLY
XA A Y SUPPLY leaf
.ends parent
'''
        network = ProbeNetwork(library)
        deck = 'V0 IN 0 0\nXM IN OUT VD parent\n'
        network.validate(deck, ['IN', 'XM:XA:control.t9', 'XM:XA:SUPPLY'])
        with self.assertRaisesRegex(ValueError, 'node'):
            network.validate(deck, ['XM:XA:control'])
        with self.assertRaisesRegex(ValueError, 'hierarchy'):
            network.validate(deck, ['XM:XB:control.t9'])

    def test_storage_probes_use_real_capacitor_plates(self):
        text = '''.subckt analog CLK VSS
X0 openlvds_dll_analog__CTRL.t9 VSS sky130_fd_pr__cap_mim_m3_1 w=10 l=10
X1 openlvds_dll_analog__CTRL.t2 VSS sky130_fd_pr__cap_mim_m3_1 w=30 l=30
X2 openlvds_dll_analog__VCOPY.t52 VSS sky130_fd_pr__cap_mim_m3_1 w=50 l=40
.ends analog
'''
        nodes = observation_nodes(text)
        self.assertEqual(nodes['CTRL'], ['openlvds_dll_analog__CTRL.t2', 'openlvds_dll_analog__CTRL.t9'])
        self.assertEqual(nodes['COPY'], ['openlvds_dll_analog__VCOPY.t52'])
        with self.assertRaises(ValueError):
            observation_nodes('.subckt empty A\n.ends empty\n')


if __name__ == '__main__':
    unittest.main()
