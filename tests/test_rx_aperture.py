# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import characterize_rx_aperture as aperture


class CaptureAperture(unittest.TestCase):
    ports = 'VGND VPWR clk data[0] data[1] reset_n serial valid'.split()

    def spec(self, edge='rising', kind='setup', polarity='rise'):
        return dict(process='tt', temperature=25, edge=edge, polarity=polarity,
                    clock_slew_ps=200, data_slew_ps=20, kind=kind)

    def synthetic(self, spec, distance, outputs=True):
        _, timing = aperture.fixture(spec, distance, self.ports)
        t = np.arange(0, timing['stop_ns'] * 1e-9 + 1e-12, 1e-12)
        phase = (t - 5e-9) / (aperture.PERIOD_NS * 1e-9)
        clock = 1.8 * ((phase % 1) < .5)
        old = 0 if spec['polarity'] == 'rise' else 1
        data = 1.8 * np.where(t < timing['transition_ns'] * 1e-9, old, 1-old)
        q0, q1 = timing['expected'] if outputs else [0, 0]
        wave = np.column_stack([np.arange(len(t)), t, clock, data,
                                np.full(len(t), q0*1.8), np.full(len(t), q1*1.8),
                                np.full(len(t), 1.8 if outputs else 0)])
        return wave, {f'V({n})': i+2 for i, n in enumerate(['CLK', 'D', 'Q0', 'Q1', 'VALID'])}, timing

    def test_every_edge_polarity_and_aperture_is_in_the_matrix(self):
        req = json.loads((aperture.ROOT/'requirements.json').read_text())
        cases = aperture.conditions(req)
        self.assertEqual(len(cases), 480)
        self.assertEqual(len({aperture.condition_id(s) for s in cases}), 480)

    def test_fixture_checks_published_pair_and_preserves_other_half(self):
        for edge in ['rising', 'falling']:
            for kind in ['setup', 'hold']:
                for polarity in ['rise', 'fall']:
                    s = self.spec(edge, kind, polarity)
                    _, timing = aperture.fixture(s, 400, self.ports)
                    new = 1 if polarity == 'rise' else 0
                    target = new if kind == 'setup' else 1-new
                    expected = [target, new] if edge == 'rising' else [1-new, target]
                    self.assertEqual(timing['expected'], expected)
                    result = aperture.measure(*self.synthetic(s, 400)[:2], s, timing, 400)
                    self.assertTrue(result['passed'], result)
                    self.assertEqual(json.loads(json.dumps(result)), result)

    def test_stuck_outputs_or_wrong_stimulus_cannot_pass(self):
        s = self.spec()
        w, h, timing = self.synthetic(s, 400, outputs=False)
        self.assertFalse(aperture.measure(w, h, s, timing, 400)['passed'])
        w, h, timing = self.synthetic(s, 400)
        self.assertIn('error', aperture.measure(w, h, s, timing, 500))

    def test_bound_keeps_guard_and_rounds_conservatively(self):
        self.assertEqual(aperture.guarded_bound(113.1), 140)
        self.assertEqual(aperture.guarded_bound(-10), 10)
        self.assertEqual(aperture.guarded_bound(-30), 0)


if __name__ == '__main__':
    unittest.main()
