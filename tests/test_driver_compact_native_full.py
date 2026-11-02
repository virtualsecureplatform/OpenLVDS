# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_driver_compact_native as full


class CompactNativeMatrixGate(unittest.TestCase):
    def test_exact_full_pvt_and_polarity_coverage(self):
        req=dict(process_corners=['tt','ff','ss','fs','sf'],temperatures_c=[0,25,40])
        points,tasks=full.tasks(req)
        self.assertEqual(len(points),15)
        self.assertEqual(len(tasks),30)
        for process,temp in points:
            self.assertEqual([t['op'] for t in tasks if (t['process'],t['temperature'])==(process,temp)],
                             ['negative_op','positive_op'])
        for changed in [dict(req,temperatures_c=[0,25,25]),dict(req,process_corners=['tt','ff','ss','fs']),
                        dict(req,temperatures_c=[0,25,40,60])]:
            with self.assertRaises(ValueError): full.tasks(changed)

    def test_partial_or_failed_pilot_cannot_prepare_full_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp)
            with patch.object(full.pilot,'verify') as verify:
                with self.assertRaises(ValueError): full.pilot_ready(parent)
                verify.assert_not_called()
            (parent/'summary.json').write_text('{}')
            with patch.object(full.pilot,'verify',return_value=dict(native_output_pilot_passed=False,passed_pvt=2)):
                with self.assertRaises(ValueError): full.pilot_ready(parent)
