from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import observe_forwarded_clock as observation


def model():
    rows = ['.subckt openlvds_tx_core clk_400 clk_90 forwarded_clock']
    for i in range(4):
        rows.append(f'XS{i} drain clock_launch_output_logic.S.t{i} source bulk sky130_fd_pr__nfet_01v8 w=1 l=.15')
    for i in range(2):
        rows.append(f'XA{i} drain clock_launch_output_drive.A.t{i} source bulk sky130_fd_pr__pfet_01v8 w=1 l=.15')
    rows += ['XC0 clock_launch_output_logic.A0.t1 gate source bulk sky130_fd_pr__nfet_01v8 w=1 l=.15',
             'XC1 drain gate clock_launch_output_logic.A1.t2 bulk sky130_fd_pr__nfet_01v8 w=1 l=.15',
             '.ends openlvds_tx_core']
    return '\n'.join(rows) + '\n'


class ForwardedClockObservation(unittest.TestCase):
    def test_all_actual_receiving_gate_endpoints_are_observed(self):
        result = observation.observations(model())
        self.assertEqual(len(result['mux_select']), 4)
        self.assertEqual(len(result['output_buffer_input']), 2)
        self.assertEqual(result['constant_high'][0]['devices'][0]['terminal'], 'D')
        self.assertEqual(result['constant_low'][0]['devices'][0]['terminal'], 'S')
        for role in ('mux_select', 'output_buffer_input'):
            self.assertTrue(all(d['terminal'] == 'G' for r in result[role] for d in r['devices']))

    def test_diffusions_or_capacitor_labels_cannot_replace_an_actual_gate(self):
        changed = model().replace('XS0 drain clock_launch_output_logic.S.t0 source',
                                  'XS0 clock_launch_output_logic.S.t0 unrelated_gate source')
        changed = changed.replace('.ends', 'CF clock_launch_output_logic.S.t0 0 1f\n.ends')
        with self.assertRaises(ValueError): observation.observations(changed)
        with self.assertRaises(ValueError): observation.observations(model().replace('clock_launch_output_logic.A1.t2', 'other_net'))

    def test_fixture_only_rebinds_include_stop_and_observations(self):
        parent, out = Path('/parent'), Path('/observation')
        deck = ('Original completed diagnostic\n.include "/parent/payload/library.spice"\n'
                'VD VDDD 0 1.8\nRD retained other 100\n.tran 1p 188.049n 0 1p\n'
                '.print tran V(TXCLOCK) V(CLK0)\n.end\n')
        probes = dict(gates=[dict(node='XTX:actual_gate')])
        changed = observation.fixture(deck, parent, out, probes)
        self.assertEqual(changed.replace('/observation/library.spice', '/parent/payload/library.spice')
            .replace('.tran 1p 120n 0 1p', '.tran 1p 188.049n 0 1p').replace(' V(XTX:actual_gate)', ''), deck)
        with self.assertRaises(ValueError): observation.fixture(deck.replace('.tran 1p', '.tran 20p'), parent, out, probes)

    def test_reproduction_checks_every_original_observation_and_tolerance(self):
        t = np.array([0, 60, 100, 120, 188.049]) * 1e-9
        reference = np.column_stack([np.arange(len(t)), t, t * 1e6, 1 + t * 1e5])
        wave = reference[:4].copy(); header = {'V(A)': 2, 'V(B)': 3}
        self.assertTrue(observation.reproduction(wave, header, reference, header)['passed'])
        changed = wave.copy(); changed[1, 3] += 2e-6
        self.assertFalse(observation.reproduction(changed, header, reference, header)['passed'])
        with self.assertRaises(ValueError): observation.reproduction(wave, {'V(A)': 2}, reference, header)

    def test_unverified_payload_cannot_prepare_an_observer(self):
        with tempfile.TemporaryDirectory() as name:
            parent = Path(name) / 'parent'
            with patch.object(observation.coupled, 'verify', return_value=dict(payload_restored=False)):
                with self.assertRaises(ValueError): observation.prepare(parent)
            self.assertEqual(list(Path(name).iterdir()), [])

    def test_prior_observation_outputs_are_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'manifest.json').write_text('{}'); (root / 'bench.raw').write_text('partial')
            with patch.object(observation, 'bound', return_value={}), patch.object(observation, 'command') as command:
                with self.assertRaisesRegex(ValueError, 'no retry'): observation.run(root)
                command.assert_not_called()
            self.assertEqual((root / 'bench.raw').read_text(), 'partial')
