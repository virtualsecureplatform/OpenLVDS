# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_driver_exact as bench


class ExactDriverBenchmark(unittest.TestCase):
    def wave(self):
        t = np.linspace(0, 2540e-9, 25401)
        a = np.zeros((len(t), 9)); a[:, 0] = np.arange(len(t)); a[:, 1] = t
        a[:, 3] = 1.2+.15*np.sin(t*2*np.pi/2.5e-9)
        a[:, 4] = 1.2-.15*np.sin(t*2*np.pi/2.5e-9)
        return a

    def test_identical_trace_passes_but_lost_edges_and_common_mode_error_fail(self):
        a = self.wave()
        self.assertTrue(bench.comparison(a, a)['passed'])
        changed = a.copy(); changed[:, 3:5] += .03
        self.assertFalse(bench.comparison(a, changed)['passed'])
        changed = a.copy(); changed[:, 3:5] = 1.2
        self.assertFalse(bench.comparison(a, changed)['passed'])
        with self.assertRaises(ValueError):
            bench.comparison(a, a[:-1])

    def test_substitution_accepts_only_resistor_changes_and_preserves_bias(self):
        bias = '.subckt lvds_bias A B\nXCB A B sky130_fd_pr__cap_mim_m3_1 w=10 l=10\n.ends lvds_bias\n'
        native = '.subckt openlvds_driver_core P N\nXC P N sky130_fd_pr__cap_mim_m3_1 w=10 l=10\nR1 P X 100\nR2 X N 200\n.ends openlvds_driver_core\n'
        exact = native.replace('R1 P X 100\nR2 X N 200', 'R1 P N 300')
        sig = bench.static_signature(bench.parse(native))
        result = bench.substitute(bias+native, exact, sig)
        self.assertEqual(bench.closure_hash(result, 'lvds_bias'), bench.closure_hash(bias+native, 'lvds_bias'))
        with self.assertRaises(ValueError):
            bench.substitute(bias+native, exact.replace('w=10', 'w=20'), sig)

    def test_partial_native_benchmark_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'build/diagnostics/driver_exact_benchmark/test'; out.mkdir(parents=True)
            tasks = [dict(id=c, files={}) for c in bench.CASES]
            for c in bench.CASES:
                (out/c).mkdir()
            raw = out/bench.CASES[0]/'bench.raw'; raw.write_bytes(b'partial retained')
            bench.atomic(out/'manifest.json', dict(identity=dict(simulator_provenance='test', code={}, inputs={}, parent='unused'), tasks=tasks))
            with patch.object(bench, 'ROOT', root), patch.object(bench, 'provenance', return_value='test'):
                with self.assertRaisesRegex(ValueError, 'Partial exact driver benchmark'):
                    bench.run(out)
            self.assertEqual(raw.read_bytes(), b'partial retained')


if __name__ == '__main__':
    unittest.main()
