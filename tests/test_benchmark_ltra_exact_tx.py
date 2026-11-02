# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_ltra_exact_tx as benchmark


class MatchedLtraExactTx(unittest.TestCase):
    def test_substitution_changes_only_the_bound_tx_resistors(self):
        raw = '.subckt openlvds_tx_core A Y VDD VSS\nR0 A B 1\nR1 B G 1\nC0 G VSS 1f\nXM Y G VSS VSS mos w=1 l=1\n.ends openlvds_tx_core\n'
        reduced = raw.replace('R0 A B 1\nR1 B G 1', 'R0 A G 2')
        suffix = '\n.subckt receiver A Q\nRKEEP A Q 100\n.ends receiver\n'
        result = benchmark.substitute(raw + suffix, raw, reduced)
        self.assertTrue(result.endswith(suffix))
        self.assertIn('R0 A G 2', result)
        for changed in [reduced.replace('1f', '2f'), reduced.replace('w=1', 'w=2')]:
            with self.assertRaisesRegex(ValueError, 'changes devices'):
                benchmark.substitute(raw + suffix, raw, changed)
        with self.assertRaisesRegex(ValueError, 'bound raw TX'):
            benchmark.substitute(reduced + suffix, raw, reduced)

    def waveform(self):
        t = np.linspace(0, 188.049e-9, 188050)
        signal = .9 + .85 * np.sin(2 * np.pi * t / 2.5e-9 + .2)
        names = ['TXCLOCK', 'TXDATA', 'RXCLOCK', 'RXDATA', 'Q0', 'Q1', 'RXVALID']
        wave = np.column_stack([np.arange(len(t)), t] + [signal] * len(names))
        return wave, {'V(' + name + ')': i + 2 for i, name in enumerate(names)}

    def test_identical_complete_switching_trace_passes(self):
        wave, headers = self.waveform()
        result = benchmark.wave_comparison(wave, headers, wave, headers)
        self.assertTrue(result['passed'])
        self.assertEqual(max(result['maximum_voltage_error_v'].values()), 0.)

    def test_voltage_error_or_missing_clock_cannot_pass(self):
        wave, headers = self.waveform()
        for changed in ['voltage', 'clock', 'timing']:
            other = wave.copy()
            if changed == 'voltage':
                other[:, headers['V(Q0)']] += .025
            elif changed == 'clock':
                other[:, headers['V(RXCLOCK)']] = 0.
            else:
                other[:, headers['V(TXCLOCK)']] = .9 + .85 * np.sin(
                    2 * np.pi * (other[:, 1] - 25e-12) / 2.5e-9 + .2)
            with self.subTest(changed=changed):
                self.assertFalse(benchmark.wave_comparison(wave, headers, other, headers)['passed'])

    def test_partial_nonfinite_or_different_columns_are_rejected(self):
        wave, headers = self.waveform()
        with self.assertRaisesRegex(ValueError, 'complete matched'):
            benchmark.wave_comparison(wave, headers, wave[:100], headers)
        bad = wave.copy()
        bad[100, 2] = np.nan
        with self.assertRaises(ValueError):
            benchmark.wave_comparison(wave, headers, bad, headers)
        with self.assertRaises(ValueError):
            benchmark.wave_comparison(wave, headers, wave, dict(headers, EXTRA=20))


if __name__ == '__main__':
    unittest.main()
