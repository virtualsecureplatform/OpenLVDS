# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_driver_finger_pcells as physical


class SourceGatedFingerPCellProbe(unittest.TestCase):
    def test_partial_source_receipt_never_invokes_magic(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(physical, 'ROOT', Path(tmp)), \
                patch.object(physical, 'invoke_magic', side_effect=AssertionError('Unqualified source drawn')):
            r = dict(source_waveform_ready=True, required_cases=6, required_pvt=3, physical_admission=False)
            name = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()[:16]
            out = Path(tmp) / 'build/diagnostics/driver_shape_source_verification' / name
            out.mkdir(parents=True)
            (out / 'summary.json').write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError, 'Full source readiness'):
                physical.build(out / 'summary.json')
            self.assertFalse((Path(tmp) / 'build/diagnostics/driver_finger_pcells').exists())
        with self.assertRaises(ValueError):
            physical.source_ready(Path('/tmp/unrelated/summary.json'))

    def test_primitive_cache_key_includes_finger_count(self):
        a = dict(model='sky130_fd_pr__pfet_g5v0d10v5', params=dict(w='8', l='.5'), nf=2)
        b = dict(a, nf=16)
        self.assertNotEqual(physical.key(a), physical.key(b))
        self.assertEqual(physical.key(a)[:3], physical.key(b)[:3])


if __name__ == '__main__':
    unittest.main()
