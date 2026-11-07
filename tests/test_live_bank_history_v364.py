# SPDX-License-Identifier: GPL-3.0-only
"""Check live projection boundaries and physically signed stage histories."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_live_bank_history_v364 as p


class LiveBankHistoryTests(unittest.TestCase):
    def waveform(self, stop=23000):
        t = np.arange(stop+1, dtype=float)
        def signal(delay):
            x = t-delay-2100
            return 1.8*((x >= 0) & (x < 8*2500) & (x % 2500 < 1250))
        return np.column_stack((t*1e-12, signal(0), 1.8-signal(100),
                                signal(200), 1.8-signal(300), signal(400)))

    def spec(self):
        return dict(cycles=8, coarse=0, fine=0, frequency_mhz=400, duty=.5)

    def test_four_inversions_keep_causal_events_and_original_quarter_limit(self):
        result = p.histories(self.waveform(), self.spec())
        for row in result['stage_histories'].values():
            self.assertTrue(row['all_eight_stage_events_captured'])
            self.assertLess(row['maximum_sum_residual_ps'], 1e-8)
            np.testing.assert_allclose(row['total_delays_ps'], 400, atol=1e-8)
            for delays in row['stage_delays_ps'].values():
                np.testing.assert_allclose(delays, 100, atol=1e-8)
        self.assertAlmostEqual(result['prefix_timing']['zero_code_fast_quarter_headroom_ps'], 1e6/410/4-400)
        self.assertFalse(result['source_waveform_complete'])
        self.assertFalse(result['native_voltage_and_control_checks_complete'])
        self.assertFalse(result['qualified_phy'])

    def test_incomplete_last_pulse_is_retained_without_inventing_events(self):
        r = p.histories(self.waveform(21000), self.spec())
        self.assertFalse(r['stage_histories']['fall']['all_eight_stage_events_captured'])
        self.assertEqual(r['stage_histories']['fall']['available_crossing_counts']['v(out)'], 7)
        self.assertIsNone(r['prefix_timing']['zero_code_fast_quarter_headroom_ps'])
        self.assertFalse(r['qualified_phy'])

    def test_reject_noncausal_stage_pairing_without_epoch_reassignment(self):
        data = self.waveform()
        data[:, 2] = 1.8-data[:, 1]
        with self.assertRaises(ValueError):
            p.histories(data, self.spec())

    def test_projection_ignores_only_partial_record_and_preserves_original_bytes(self):
        data = self.waveform(5)
        names = (*p.NODES, 'v(unchecked)')
        source = np.column_stack((data, np.full(len(data), np.nan)))
        header = ('Title: live\nFlags: real\nNo. Variables: 7\nNo. Points: 0\nVariables:\n'+
                  ''.join(f'\t{k}\t{name}\t'+('time' if k == 0 else 'voltage')+'\n'
                          for k, name in enumerate(names))+'Binary:\n').encode()
        payload = source.astype('<f8').tobytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'bench.raw'
            original = header+payload+b'partial'
            path.write_bytes(original)
            actual_header, selected, metadata = p.project(path)
            np.testing.assert_array_equal(selected, data)
            self.assertEqual(actual_header, header)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(metadata['ignored_partial_frame_bytes'], 7)
            self.assertEqual(metadata['complete_record_payload_sha256'], hashlib.sha256(payload).hexdigest())
            source[1, 2] = np.nan
            path.write_bytes(header+source.astype('<f8').tobytes())
            with self.assertRaises(ValueError):
                p.project(path)


if __name__ == '__main__':
    unittest.main()
