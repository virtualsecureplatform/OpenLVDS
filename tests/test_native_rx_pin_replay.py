# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_native_rx_pins as replay


class NativeRxPinReplay(unittest.TestCase):
    def wave(self):
        t = np.linspace(0, 150e-9, 1501)
        values = [(np.sin(t*2*np.pi/10e-9) > 0)*1.8,
                  (np.cos(t*2*np.pi/10e-9) > 0)*1.8,
                  np.zeros(len(t)), np.ones(len(t))*1.8, np.ones(len(t))*1.8]
        return np.column_stack([np.arange(len(t)), t, *values]), {
            'INDEX': 0, 'TIME': 1, **{'V('+n+')': i+2 for i, n in enumerate(replay.NAMES)}}

    def test_every_recorded_pin_vertex_preserved_without_voltage_clipping(self):
        w, h = self.wave(); w[12, 2] = -.1; w[13, 3] = 1.95
        text = replay.sources(w, h)
        for n in replay.NAMES[:2]:
            row = next(r for r in text.splitlines() if r.startswith('VREC_'+n+' '))
            actual = np.array([float(v) for v in row.split('PWL(')[1][:-1].split()]).reshape(-1, 2)
            np.testing.assert_array_equal(actual[:, 0], w[:, 1])
            np.testing.assert_array_equal(actual[:, 1], w[:, h['V('+n+')']])
        w[1, 1] = w[0, 1]
        with self.assertRaises(ValueError):
            replay.sources(w, h)

    def test_fixture_keeps_native_rx_and_removes_analog_instances(self):
        parent = '''Parent
.lib "/pdk/sky130.lib.spice" ss
.options device temp=40
.options timeint method=gear reltol=1e-4 abstol=1e-12
VDIG VDDD 0 1.8
VRST RESET_N 0 PWL(0 0 2n 0 2.1n 1.8)
XDR input output receiver
XRX 0 VDDD RXCLOCK Q0 Q1 RESET_N RXDATA RXVALID openlvds_ddr_rx
CQ0 Q0 0 20f
CQ1 Q1 0 20f
'''
        deck = replay.fixture(parent, Path('/isolated'), 188.049e-9)
        for row in parent.splitlines()[1:]:
            if not row.startswith('XDR'):
                self.assertIn(row, deck)
        self.assertNotIn('XDR', deck)
        self.assertIn('.tran 5p ', deck)
        with self.assertRaises(ValueError):
            replay.fixture(parent+'CQ0 Q0 0 20f\n', Path('/isolated'), 188e-9)

    def test_comparison_detects_missing_edges_and_reports_constant_output_mismatch(self):
        w, h = self.wave()
        self.assertTrue(replay.compare(w, h, w, h)['all_edge_counts_and_times_agree'])
        changed = w.copy(); changed[:, h['V(RXCLOCK)']] = 0
        self.assertFalse(replay.compare(w, h, changed, h)['all_edge_counts_and_times_agree'])
        changed = w.copy(); changed[:, h['V(Q0)']] = 1.8
        result = replay.compare(w, h, changed, h)
        self.assertEqual(result['vectors']['Q0']['maximum_interpolated_voltage_error_v'], 1.8)
        with self.assertRaises(ValueError):
            replay.complete(w[:-400], h, 150e-9)

    def test_partial_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'build/diagnostics/native_rx_pin_replay/test'; root.mkdir(parents=True)
            (root/'bench.raw').write_text('retained partial')
            m = dict(identity=dict(simulator_provenance='test', code={}, inputs={}), files={})
            replay.atomic(root/'manifest.json', m)
            with patch.object(replay, 'ROOT', Path(tmp)), patch.object(replay, 'provenance', return_value='test'):
                with self.assertRaisesRegex(ValueError, 'Partial native RX replay retained'):
                    replay.run(root)
            self.assertEqual((root/'bench.raw').read_text(), 'retained partial')


if __name__ == '__main__':
    unittest.main()
