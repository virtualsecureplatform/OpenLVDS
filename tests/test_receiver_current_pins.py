# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_receiver_current_pins as replay


class ReceiverCurrentPins(unittest.TestCase):
    def test_all_original_knots_and_voltages_preserved_with_fixed_time_shift(self):
        t = np.array([0, 50, 50.003, 50.0037, 79.9832, 119.991, 120, 188.049])*1e-9
        w = np.column_stack([np.arange(len(t)), t, *[1.2+.2*np.sin(t*1e9+i) for i in range(4)]])
        h = {'V('+n+')': i+2 for i, n in enumerate(replay.PINS)}
        rows, proof = replay.recorded(w, h)
        self.assertFalse(proof['resampling'])
        for n, row in rows.items():
            a = np.array([float(v) for v in row.split('PWL(')[1][:-1].split()]).reshape(-1, 2)
            keep = (t >= 50e-9-8*np.spacing(50e-9)) & (t <= 120e-9+8*np.spacing(120e-9))
            np.testing.assert_array_equal(a[1:, 0], t[keep]-45e-9)
            np.testing.assert_array_equal(a[1:, 1], w[keep, h['V('+n+')']])
            self.assertGreater(np.diff(a[:, 0]).min(), 1e-15)
        with self.assertRaises(ValueError):
            replay.recorded(w[:-2], h)

    def test_only_four_pin_sources_and_library_path_change(self):
        rows = {n: 'V'+n+' '+n+' 0 PWL(0 1.2 75n 1.3)' for n in replay.PINS}
        original = ('Original\n.include "/old/library.spice"\n'+
                    '\n'.join('V'+n+' '+n+' 0 PWL(0 1 75n 2)' for n in replay.PINS)+
                    '\nXRC pins unchanged\n.tran 5p 80n 0 1p\n.print tran V(RXCLOCK)\n.end\n')
        actual = replay.fixture(original, Path('/old'), Path('/new'), rows)
        for n in replay.PINS:
            actual = actual.replace(rows[n], 'V'+n+' '+n+' 0 PWL(0 1 75n 2)')
        self.assertEqual(actual.replace('/new/', '/old/'), original)
        with self.assertRaises(ValueError):
            replay.fixture(original.replace('80n', '40n'), Path('/old'), Path('/new'), rows)

    def test_partial_replay_is_retained_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p = root/'build/diagnostics/receiver_current_pins/test'; p.mkdir(parents=True)
            replay.atomic(p/'manifest.json', dict(identity=dict(simulator_provenance='test', code={}, inputs={}), files={}))
            raw = p/'bench.raw'; raw.write_bytes(b'partial retained')
            with patch.object(replay, 'ROOT', root), patch.object(replay, 'provenance', return_value='test'):
                with self.assertRaisesRegex(ValueError, 'Partial current-pin receiver replay'):
                    replay.run(p)
            self.assertEqual(raw.read_bytes(), b'partial retained')


if __name__ == '__main__':
    unittest.main()
