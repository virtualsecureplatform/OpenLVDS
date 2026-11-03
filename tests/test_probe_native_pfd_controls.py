from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_native_pfd_controls as baseline


class NativePFDControlBaseline(unittest.TestCase):
    def test_failed_native_reference_gate_does_not_prepare_an_experiment(self):
        with tempfile.TemporaryDirectory() as d,patch.object(baseline.assembly,'reference_gate',side_effect=ValueError('changed context')):
            root=Path(d)
            with self.assertRaises(ValueError):baseline.prepare(root/'q')
            self.assertEqual(list(root.iterdir()),[])

    def test_partial_output_is_preserved_without_another_lease(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'manifest.json').write_text('{}');(out/'bench.raw').write_bytes(b'partial')
            with patch.object(baseline,'bound',return_value={}),patch.object(baseline,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):baseline.run(out)
                lease.assert_not_called()
