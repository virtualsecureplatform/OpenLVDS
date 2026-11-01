# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_receiver_restoration as observation


class ReceiverRestorationObservation(unittest.TestCase):
    def test_distinguishes_first_restorer_from_later_stage_loss(self):
        t = np.linspace(0, 12e-9, 12001)
        differential = .3*np.cos(2*np.pi*t/4e-9)
        output = np.full_like(t, 1.8)
        transport = observation.pulse_transport(t, differential, output, 0, 12e-9)
        nodes = dict(CO=np.full_like(t, .78), RESTORE0=np.full_like(t, 1.75),
                     RESTORE1=np.zeros_like(t), RXCLOCK=output)
        rows = observation.falling_windows(t, differential, nodes, transport)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['output_edges_in_next_input_period'] == 0 and
                            r['first_restorer_falling_crossings'] == 0 for r in rows))
        # The output still fails, but a switching first restorer must not be
        # labelled as the same failure as the non-switching stage above.
        nodes['RESTORE0'] = np.where(differential < -.05, .1, 1.8)
        switched = observation.falling_windows(t, differential, nodes, transport)
        self.assertTrue(all(r['first_restorer_falling_crossings'] == 1 for r in switched))
        self.assertTrue(all(r['output_edges_in_next_input_period'] == 0 for r in switched))

    def test_next_pulse_does_not_enter_previous_response_window(self):
        t = np.linspace(0, 12e-9, 12001); differential = .3*np.cos(2*np.pi*t/4e-9)
        output = np.full_like(t, 1.8)
        transport = observation.pulse_transport(t, differential, output, 0, 12e-9)
        nodes = dict(CO=np.where(t < 5.01e-9, .7, 1.7), RESTORE0=output,
                     RESTORE1=np.zeros_like(t), RXCLOCK=output)
        rows = observation.falling_windows(t, differential, nodes, transport)
        self.assertAlmostEqual(rows[0]['co_peak_v'], .7)
        self.assertAlmostEqual(rows[1]['co_peak_v'], 1.7)

    def test_partial_replay_cannot_be_observed_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(observation, 'ROOT', Path(tmp)):
            root = Path(tmp)/'build/diagnostics/receiver_replay/partial'; root.mkdir(parents=True)
            (root/'bench.raw').write_bytes(b'original partial')
            with self.assertRaisesRegex(ValueError, 'Complete both full native'):
                observation.diagnose(root)
            self.assertEqual((root/'bench.raw').read_bytes(), b'original partial')


if __name__ == '__main__':
    unittest.main()
