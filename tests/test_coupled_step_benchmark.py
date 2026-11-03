from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_coupled_step as benchmark


class CoupledStepBenchmark(unittest.TestCase):
    def waveform(self):
        t = np.linspace(0, 188.049e-9, 40001)
        clock = 1.8 * ((t % 2.5e-9) < 1.25e-9)
        values = {n: np.full(len(t), 1.2) for n in benchmark.IO}
        values.update({n: clock.copy() for n in benchmark.DIGITAL})
        values['TXREADY'] = np.full(len(t), 1.8); values['RXVALID'] = np.full(len(t), 1.8)
        wave = np.column_stack([np.arange(len(t)), t, *values.values()])
        return wave, {f'V({n})': i + 2 for i, n in enumerate(values)}

    def test_fixture_changes_only_maximum_step_and_include(self):
        deck = 'same native\n.include "/parent/payload/library.spice"\nRD a b 100\n.tran 1p 188.049n 0 1p\n.end\n'
        new = benchmark.fixture(deck, Path('/parent'), Path('/new'))
        self.assertEqual(new.replace('/new/library.spice', '/parent/payload/library.spice')
            .replace('.tran 1p 188.049n 0 5p', '.tran 1p 188.049n 0 1p'), deck)
        with self.assertRaises(ValueError): benchmark.fixture(deck.replace('188.049n', '12n'), Path('/parent'), Path('/new'))

    def test_identical_traces_pass_without_phy_or_model_promotion(self):
        wave, header = self.waveform(); result = benchmark.compare(wave, header, wave, header)
        self.assertTrue(result['passed'])
        self.assertEqual(result['io_error_limit_v'], .01); self.assertEqual(result['edge_error_limit_ps'], 2.5)

    def test_io_voltage_error_or_missing_original_observation_rejected(self):
        wave, header = self.waveform(); changed = wave.copy(); changed[:, header['V(RP)']] += .011
        self.assertFalse(benchmark.compare(wave, header, changed, header)['passed'])
        short = dict(header); short.pop('V(RP)')
        with self.assertRaises(ValueError): benchmark.compare(wave, header, wave, short)

    def test_missing_or_late_clock_edges_rejected(self):
        t = np.arange(0, 125.001, .001) * 1e-9
        reference = 1.8 * ((t % 2.5e-9) < 1.25e-9)
        late = 1.8 * (((t - .005e-9) % 2.5e-9) < 1.25e-9)
        self.assertFalse(benchmark.crossings(t, reference, t, late, .9)['passed'])
        self.assertFalse(benchmark.crossings(t, reference, t, np.zeros(len(t)), .9)['passed'])

    def test_wrong_constant_ready_level_cannot_pass_with_zero_edge_counts(self):
        wave, header = self.waveform(); changed = wave.copy(); changed[:, header['V(TXREADY)']] = 0
        result = benchmark.compare(wave, header, changed, header)
        self.assertTrue(result['edge_checks']['TXREADY']['passed'])
        self.assertFalse(result['digital_level_checks']['TXREADY']['passed']); self.assertFalse(result['passed'])

    def test_truncated_or_nonfinite_waveforms_rejected(self):
        wave, header = self.waveform()
        with self.assertRaises(ValueError): benchmark.compare(wave, header, wave[:-1], header)
        changed = wave.copy(); changed[0, 2] = float('nan')
        with self.assertRaises(ValueError): benchmark.compare(wave, header, changed, header)

    def test_failed_payload_retains_its_diagnosis_without_a_missing_margin_error(self):
        reference = dict(payload_restored=True, payload=dict(checked_bits=32, setup_margin_ps=210, hold_margin_ps=220))
        candidate = dict(payload_restored=False, payload=dict(error='No correctly ordered payload preamble'))
        with patch.object(benchmark.coupled.baseline, 'completed_export', return_value=(np.zeros((2, 2)), {})), \
             patch.object(benchmark, 'compare', return_value=dict(passed=False)), \
             patch.object(benchmark.coupled, 'payload', side_effect=[reference, candidate]):
            result = benchmark.measure(Path('candidate'), dict(identity=dict(parent='reference')))
            self.assertFalse(result['coupled_step_equivalence_passed'])
            self.assertIsNone(result['margin_error_ps']['setup'])
            self.assertEqual(result['candidate']['payload']['error'], 'No correctly ordered payload preamble')

    def test_unverified_reference_and_prior_outputs_cannot_dispatch(self):
        with patch.object(benchmark.coupled, 'verify', return_value=dict(payload_restored=False)):
            with self.assertRaises(ValueError): benchmark.prepare(Path('unverified'))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'manifest.json').write_text('{}'); (root / 'bench.raw').write_text('partial')
            with patch.object(benchmark, 'bound', return_value={}), patch.object(benchmark, 'command') as command:
                with self.assertRaisesRegex(ValueError, 'no retry'): benchmark.run(root)
                command.assert_not_called()
