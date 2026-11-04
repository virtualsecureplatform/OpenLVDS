# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import clocking_v2 as v2


class ClockingV2Tests(unittest.TestCase):
    def test_protocol_marker_is_cyclically_unique(self):
        frame = v2.training_frame()
        self.assertEqual(len(frame), 256)
        self.assertEqual(v2.marker_positions(frame), [0])
        self.assertEqual(v2.marker_positions(frame, v2.END_MARKER), [])

    def test_all_serial_rotations_and_pair_orientations(self):
        frame = v2.training_frame()
        for rotation in range(256):
            stream = (frame * 6)[rotation:rotation+1280]
            self.assertEqual(v2.align_training(stream), [(-rotation) % 256])
            damaged = list(stream); damaged[600] ^= 1
            self.assertEqual(v2.align_training(damaged), [])

    def test_physical_eye_midpoint_not_code_midpoint(self):
        # Dense codes on the left make the code midpoint the wrong choice.
        positions = list(range(0, 300, 5)) + list(range(300, 901, 15))
        table = [v2.Delay(i, p, p+1) for i, p in enumerate(positions)]
        result = v2.select_eye(table, [True] * len(table))
        self.assertEqual(result['delay_interval_ps'], [450, 451])
        self.assertGreater(result['code'], len(table)//2)

    def test_narrow_and_split_eyes_rejected(self):
        table = [v2.Delay(i, i*10, i*10+1) for i in range(100)]
        with self.assertRaises(ValueError):
            v2.select_eye(table, [i < 45 for i in range(100)])
        with self.assertRaises(ValueError):
            v2.select_eye(table, [i < 40 or i > 60 for i in range(100)])

    def test_uncertainty_and_pvt_reversal_cannot_be_hidden(self):
        good = [v2.Delay(i, i*10, i*10+1) for i in range(4)]
        self.assertEqual(v2.common_legal_codes({'tt': good, 'ss': good}), (0,1,2,3))
        for bad in [list(reversed(good)), [v2.Delay(i, i*30, i*30+1) for i in range(4)]]:
            with self.assertRaises(ValueError): v2.common_legal_codes({'tt': good, 'ss': bad})
        with self.assertRaises(ValueError):
            v2.common_legal_codes({'tt': [v2.Delay(0, 0, 11), v2.Delay(1, 10, 12)]})

    def test_tagged_confirmation_cannot_be_inferred_from_code_search(self):
        tables = [[400+i*10+offset for i in range(40)] for offset in (0,2,4,6)]
        result = v2.balance_sections(tables, 2500)
        self.assertLessEqual(abs(result['period_error_ps']), 20)
        self.assertFalse(result['locked'])
        with self.assertRaises(ValueError): v2.balance_sections(tables, 5000)
        with self.assertRaises(ValueError): v2.balance_sections(tables, 1250)

    def test_coarse_backoff_fine_does_not_wrap(self):
        values = [10*i for i in range(101)]
        for target in range(1001):
            low, high = v2.crossing_search(values, target)
            self.assertLessEqual(values[low], target)
            self.assertGreaterEqual(values[high], target)
            self.assertLessEqual(high-low, 1)
        with self.assertRaises(ValueError): v2.crossing_search(values, 1001)

    def test_fixed_lab_policy(self):
        root = Path(__file__).resolve().parents[1]
        policy = json.loads((root / 'clocking_v2.json').read_text())
        self.assertFalse(policy['qualified_phy'])
        self.assertEqual(policy['timing']['timeout_management_cycles'], 25_000*100)
        self.assertEqual(policy['timing']['payload_margin_ps'], 200)
