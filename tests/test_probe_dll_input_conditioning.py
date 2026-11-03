# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_dll_input_conditioning as probe

PORTS = ['A', 'VGND', 'VNB', 'VPB', 'VPWR', 'X']
DECK = '''Original slew fixture
.include "/old/full.spice"
VA VDDIO 0 3.3
VD VDDD 0 1.8
IB PB 0 35u
VREF REF 0 PULSE(0 1.8 4.99n 20p 20p 1.23n 2.5n)
VFDB FDB 0 PULSE(0 1.8 4.95n 200p 200p 1.05n 2.5n)
XP REF FDB RST VDDD UP DN VDDD 0 lvds_pfd
.save i(VA) i(VD)
.tran 5p 160n 0 20p
.print tran V(UP) V(DN) V(BAD) V(UF) V(DF) V(REF) V(FDB)
.end
'''


class DLLInputConditioning(unittest.TestCase):
    def test_only_two_buffers_clock_connections_include_and_observations_change(self):
        result = probe.fixture(DECK, Path('/old'), Path('/new'), PORTS)
        self.assertIn('XCOND_REF REF 0 0 VDDD VDDD REF_FAST ' + probe.CELL, result)
        self.assertIn('XCOND_FDB FDB 0 0 VDDD VDDD FDB_FAST ' + probe.CELL, result)
        restored = '\n'.join(row for row in result.splitlines() if not row.startswith('XCOND_'))+'\n'
        restored = restored.replace('"/new/library.spice"', '"/old/full.spice"').replace(
            'XP REF_FAST FDB_FAST', 'XP REF FDB').replace(' V(REF_FAST) V(FDB_FAST)', '')
        self.assertEqual(restored, DECK)

    def test_changed_integration_ports_or_preexisting_conditioned_node_are_rejected(self):
        for deck, ports in [(DECK.replace('0 20p', '0 40p'), PORTS),
                            (DECK.replace('XP REF FDB', 'XP FDB REF'), PORTS),
                            (DECK, PORTS[:-1]),
                            (DECK.replace('.end', 'VEXTRA REF_FAST 0 0\n.end'), PORTS)]:
            with self.assertRaises(ValueError): probe.fixture(deck, Path('/old'), Path('/new'), ports)

    def waveform(self, offset=50, missing=False):
        t = np.linspace(0, 160e-9, 16001)
        def clock(delay): return .9 + .9*np.sin(2*np.pi*400e6*(t-delay))
        values = [np.zeros(len(t)), np.zeros(len(t)), np.zeros(len(t)), np.ones(len(t)),
                  np.full(len(t), .4), np.full(len(t), .364), clock(5e-9),
                  clock(5e-9+offset*1e-12), clock(5.1e-9),
                  np.zeros(len(t)) if missing else clock(5.1e-9+offset*1e-12)]
        w = np.column_stack([np.arange(len(t)), t] + values)
        names = ['UP', 'DN', 'BAD', 'CTRL', 'UF', 'DF', 'REF', 'FDB', 'REF_FAST', 'FDB_FAST']
        h = {'V('+n+')': i+2 for i, n in enumerate(names)}
        return w, h

    def task(self, offset):
        return dict(spec={'offset_ps': offset}, aliases={n:n for n in
                    ['UP', 'DN', 'BAD', 'CTRL', 'UF', 'DF', 'REF', 'FDB']})

    def test_original_valid_phase_and_fault_thresholds_are_retained(self):
        with patch.object(probe, 'completed', return_value=self.waveform(50)):
            r = probe.measure(Path('/unused'), self.task(50))
        self.assertTrue(r['passed']); self.assertAlmostEqual(r['conditioned_phase_mean_ps'], 50, places=6)
        with patch.object(probe, 'completed', return_value=self.waveform(150)):
            r = probe.measure(Path('/unused'), self.task(150))
        self.assertFalse(r['passed']); self.assertTrue(r['expected_bad'])

    def test_missing_conditioned_clock_cannot_use_original_clock_as_fallback(self):
        with patch.object(probe, 'completed', return_value=self.waveform(missing=True)):
            with self.assertRaisesRegex(ValueError, 'missing clock cycles'):
                probe.measure(Path('/unused'), self.task(50))

    def test_partial_run_cannot_dispatch_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out/'state.json').write_text('{"status":"running"}')
            (out/'manifest.json').write_text('{}')
            with patch.object(probe, 'bound', return_value={'tasks': []}), \
                    patch.object(probe, 'lease') as lease:
                with self.assertRaisesRegex(ValueError, 'no retry'): probe.run(out)
                lease.assert_not_called()

    def test_duplicate_passes_cannot_hide_missing_fault_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out/'manifest.json').write_text('{"identity":{"scope":"diagnostic"}}')
            rows = [{'task': n, 'passed': True} for n in probe.CASES]
            self.assertTrue(probe.aggregate(out, rows)['input_conditioning_diagnostic_passed'])
            self.assertFalse(probe.aggregate(out, [rows[0]]*3)['input_conditioning_diagnostic_passed'])


if __name__ == '__main__':
    unittest.main()
