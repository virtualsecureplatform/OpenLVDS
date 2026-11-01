# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_receiver_replay as probe


class ReceiverReplayObservations(unittest.TestCase):
    def test_every_retained_fragment_is_observed_and_missing_nets_are_refused(self):
        rows = ['.subckt openlvds_ddr_rx VGND VPWR clk Q0 Q1 reset_n serial valid']
        rows += [f'C{i} {n} VGND 1f' for i, n in enumerate(probe.LEAVES)]
        rows += ['R0 rise_enable.A rise_enable.A.t0 1', 'CEX rise_enable.A.t0 VGND 1f',
                 'R1 rise_enable.A.t0 rise_enable.A.n0 1', 'CEX2 rise_enable.A.n0 VGND 1f', '.ends openlvds_ddr_rx']
        library = '\n'.join(rows)
        nodes = probe.aliases(library)
        for n in ['rise_enable.A', 'rise_enable.A.t0', 'rise_enable.A.n0']:
            self.assertIn('XRX:'+n, nodes)
        self.assertIn('XCR:openlvds_receiver_core__CO', nodes)
        self.assertNotIn('XRX:serial', nodes)
        self.assertNotIn('XRX:clk', nodes)
        with self.assertRaises(ValueError):
            probe.aliases(library.replace('fall_enable.A', 'unrelated'))

    def test_only_print_vectors_change(self):
        deck = 'Control\n.options itl4=100\n.tran 5p 188n 0 5p\n.print tran V(RP) V(RN)\n.end\n'
        observed = probe.add_probes(deck, ['XRX:held_rise.Q', 'XCR:openlvds_receiver_core__CO'])
        self.assertEqual(observed.replace(' V(XRX:held_rise.Q) V(XCR:openlvds_receiver_core__CO)', ''), deck)
        with self.assertRaises(ValueError):
            probe.add_probes(deck+deck, ['XRX:held_rise.Q'])


if __name__ == '__main__':
    unittest.main()
