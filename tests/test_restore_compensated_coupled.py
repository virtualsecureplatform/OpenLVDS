# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import restore_compensated_coupled as restore
from dll_campaign import text_block
from spice_scope import closure_hash


class CompensatedCoupledRestoration(unittest.TestCase):
    def model(self, resistance=100):
        blocks = [f'.subckt {restore.TOP} D P N VR PB NB VA VD VS\nRDR P N {resistance}\n.ends {restore.TOP}']
        for name in ['lvds_bias', 'openlvds_tx_core', 'openlvds_receiver_core', 'openlvds_ddr_rx']:
            ports = 'IREF NB VA VS' if name == 'lvds_bias' else 'A B'
            blocks.append(f'.subckt {name} {ports}\nR0 {ports.split()[0]} {ports.split()[1]} 10\n.ends {name}')
        return '\n'.join(blocks)

    def deck(self):
        return f'''Coupled fixture
.include "/old/library.spice"
IREF_TX IREF_TX 0 35u
IREF_RX IREF_RX 0 35u
XBT IREF_TX NBT VA 0 lvds_bias
XBR IREF_RX NBR VA 0 lvds_bias
XDT D P N VR IREF_TX NBT VA VD 0 {restore.TOP}
XCT C CP CN VR IREF_TX NBT VA VD 0 {restore.TOP}
VCLK0 C 0 PULSE(0 1.8 5n .1n .1n 1n 2.5n)
.tran 1p 188.049n 0 1p
.print tran V(P) V(N) V(CP) V(CN)
.end
'''

    def test_driver_change_preserves_all_other_circuit_closures(self):
        original, candidate = self.model(), self.model(120)
        changed = restore.substitute(original, candidate, self.deck())
        self.assertEqual(text_block(changed, restore.TOP), text_block(candidate, restore.TOP))
        for name in ['lvds_bias', 'openlvds_tx_core', 'openlvds_receiver_core', 'openlvds_ddr_rx']:
            self.assertEqual(closure_hash(changed, name), closure_hash(original, name))

    def test_wrong_port_order_bias_or_reference_cannot_enter_coupled_fixture(self):
        original = self.model()
        for model, deck in [(self.model(120).replace(' D P N VR', ' D N P VR'), self.deck()),
                (self.model(120).replace('R0 IREF NB 10', 'R0 IREF NB 11'), self.deck()),
                (self.model(120), self.deck().replace('IREF_TX IREF_TX 0 35u', 'IREF_TX IREF_TX 0 70u')),
                (self.model(120), self.deck().replace('.end', 'XEXTRA IREF_TX NBT VA 0 lvds_bias\n.end'))]:
            with self.subTest(deck=deck):
                with self.assertRaises(ValueError):
                    restore.substitute(original, model, deck)

    def test_short_fixture_changes_only_include_and_stop(self):
        deck = self.deck()
        for stop in [12, 188.049]:
            result = restore.fixture(deck, Path('/old'), Path('/new'), stop)
            self.assertEqual(result.replace('/new/library.spice', '/old/library.spice').replace(
                f'.tran 1p {stop}n 0 1p', '.tran 1p 188.049n 0 1p'), deck)
        with self.assertRaises(ValueError):
            restore.fixture(deck.replace('0 1p', '0 20p'), Path('/old'), Path('/new'), 12)

    def test_native_pilot_alone_cannot_substitute_for_full_native_qualification(self):
        with patch.object(restore.native, 'verify', return_value=dict(native_output_matrix_passed=True,
                required_cases=6, required_pvt=3, passed_pvt=3)), patch.object(restore.components, 'verify') as component:
            with self.assertRaisesRegex(ValueError, 'thirty-case native'):
                restore.driver_gate(Path('/matrix'), Path('/components'))
            component.assert_not_called()

    def test_failed_long_components_block_coupled_preparation(self):
        with patch.object(restore.native, 'verify', return_value=dict(native_output_matrix_passed=True,
                required_cases=30, required_pvt=15, passed_pvt=15)), patch.object(restore.components, 'verify',
                return_value=dict(passed=False, required=30, passed_cases=29)), patch.object(restore.native, 'bound') as bound:
            with self.assertRaisesRegex(ValueError, 'thirty passing long'):
                restore.driver_gate(Path('/matrix'), Path('/components'))
            bound.assert_not_called()

    def test_receiver_pass_flag_cannot_admit_a_missing_rc_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rx = root / 'receiver-context'
            rx.mkdir()
            (root / 'requirements.json').write_text('{}')
            m = dict(identity=dict(campaign='receiver-components', simulator_provenance='runtime'),
                full_inputs={}, fast_inputs={})
            (rx / 'manifest.json').write_text(json.dumps(m))
            saved = dict(artifact='build/rc_validation/ngspice/receiver/missing',
                scope_sha256='scope', trace_evidence_sha256='absent')
            (rx / 'summary.json').write_text(json.dumps(dict(receiver_rc_passed=True,
                manifest_sha256=restore.sha(rx / 'manifest.json'), case={'reference': saved})))
            with patch.object(restore, 'ROOT', root), patch.object(restore.receiver_rc, 'prepare', return_value=rx):
                with self.assertRaisesRegex(ValueError, 'trace changed or incomplete'):
                    restore.receiver_gate(rx)

    def test_successful_but_unmatched_campaigns_are_rejected(self):
        with patch.object(restore.native, 'verify', return_value=dict(native_output_matrix_passed=True,
                required_cases=30, required_pvt=15, passed_pvt=15)), patch.object(restore.components, 'verify',
                return_value=dict(passed=True, required=30, passed_cases=30)), \
                patch.object(restore.native, 'bound', return_value={'identity': {'pilot': 'a'}}), \
                patch.object(restore.components, 'bound', return_value={'identity': {'pilot': 'b'}}):
            with self.assertRaisesRegex(ValueError, 'different pilots'):
                restore.driver_gate(Path('/matrix'), Path('/components'))

    def test_payload_requires_one_to_one_valid_width_clock_and_legal_pins(self):
        pulses = [dict(polarity=p, output_edges_in_next_input_period=1) for p in ['rising', 'falling'] for _ in range(20)]
        widths = {p: dict(count=21, minimum_ps=900) for p in ['high', 'low']}
        wave = np.zeros((3, 7))
        wave[:, 2:] = 1.2
        headers = {f'V({name})': i + 2 for i, name in enumerate(['RXCLOCK', 'RP', 'RN', 'RCP', 'RCN'])}
        policy = dict(pin_range_v=[0, 2.4], native_screen={'minimum_valid_pulse_ps': 400})
        with patch.object(restore.baseline, 'payload_metrics', return_value=({'passed': True}, {'pulses': pulses})), \
                patch.object(restore.baseline, 'completed_export', return_value=(wave, headers)), \
                patch.object(restore.receiver, 'valid_widths', return_value=widths), \
                patch.object(restore.receiver, 'policy', return_value=policy):
            result = restore.payload(Path('/payload'))
            self.assertTrue(result['payload_restored'])
            self.assertFalse(result['actual_dll_phase_qualified'])
            self.assertFalse(result['training_cycles_qualified'])
            self.assertFalse(result['sampling_margin_qualified'])
            pulses[0]['output_edges_in_next_input_period'] = 2
            self.assertFalse(restore.payload(Path('/payload'))['payload_restored'])
            pulses[0]['output_edges_in_next_input_period'] = 1
            widths['high']['minimum_ps'] = 399
            self.assertFalse(restore.payload(Path('/payload'))['payload_restored'])
            widths['high']['minimum_ps'] = 900
            wave[1, headers['V(RCP)']] = 2.5
            self.assertFalse(restore.payload(Path('/payload'))['payload_restored'])

    def test_numerical_short_failure_prevents_payload_dispatch_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'manifest.json').write_text('{}')
            for case in ['short', 'payload']:
                (out / case).mkdir()
            manifest = dict(identity={'scope': 'diagnostic'}, tasks=[
                dict(id='short', stop_ns=12), dict(id='payload', stop_ns=188.049)])
            result = subprocess.CompletedProcess([], 1, '', 'numerical failure')
            with patch.object(restore, 'context', return_value=manifest), \
                    patch.object(restore, 'lease') as lease, patch.object(restore, 'command', return_value=['ngspice']), \
                    patch.object(restore.subprocess, 'run', return_value=result) as run:
                restore.run(out)
                self.assertEqual(run.call_count, 1)
                report = json.loads((out / 'summary.json').read_text())
                self.assertFalse(report['payload_restored'])
                self.assertFalse(report['qualified_phy'])
                self.assertEqual([r['task'] for r in report['results']], ['short'])
                with self.assertRaisesRegex(ValueError, 'Prior or partial'):
                    restore.run(out)
                self.assertEqual(run.call_count, 1)

    def test_manifest_mutation_during_run_stops_further_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'manifest.json').write_text('{}')
            for case in ['short', 'payload']:
                (out / case).mkdir()
            manifest = dict(identity={'scope': 'diagnostic'}, tasks=[
                dict(id='short', stop_ns=12), dict(id='payload', stop_ns=188.049)])
            def mutate(*args, **kwargs):
                (out / 'manifest.json').write_text('{"changed":true}')
                return subprocess.CompletedProcess([], 0, '', '')
            with patch.object(restore, 'context', return_value=manifest), patch.object(restore, 'lease'), \
                    patch.object(restore, 'command', return_value=['ngspice']), \
                    patch.object(restore.subprocess, 'run', side_effect=mutate) as run:
                with self.assertRaisesRegex(ValueError, 'manifest changed'):
                    restore.run(out)
                self.assertEqual(run.call_count, 1)
                self.assertFalse((out / 'payload/summary.json').exists())

    def test_analysis_failure_does_not_relabel_completed_numerical_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'manifest.json').write_text('{}')
            for case in ['short', 'payload']:
                (out / case).mkdir()
            manifest = dict(identity={'scope': 'diagnostic'}, tasks=[
                dict(id='short', stop_ns=12), dict(id='payload', stop_ns=188.049)])
            with patch.object(restore, 'context', return_value=manifest), patch.object(restore, 'lease'), \
                    patch.object(restore, 'command', return_value=['ngspice']), \
                    patch.object(restore.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
                    patch.object(restore.baseline, 'completed_export'), \
                    patch.object(restore, 'payload', side_effect=ValueError('analysis failed')):
                restore.run(out)
                row = json.loads((out / 'payload/summary.json').read_text())
                self.assertTrue(row['numerically_completed'])
                self.assertEqual(row['error'], 'analysis failed')
                self.assertFalse(json.loads((out / 'summary.json').read_text())['payload_restored'])

    def test_independent_verification_rejects_changed_data_or_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'manifest.json').write_text('{}')
            stamp = restore.sha(out / 'manifest.json')
            manifest = dict(identity={'scope': 'diagnostic'}, tasks=[
                dict(id='short', stop_ns=12), dict(id='payload', stop_ns=188.049)])
            rows = []
            measurement = {'payload_restored': True}
            for task in manifest['tasks']:
                folder = out / task['id']
                folder.mkdir()
                names = ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log']
                for name in names:
                    (folder / name).write_text('captured')
                row = dict(task=task['id'], returncode=0, error=None, numerically_completed=True,
                    manifest_sha256=stamp, measurements=measurement if task['id'] == 'payload' else None,
                    files={n: restore.sha(folder / n) for n in names})
                (folder / 'summary.json').write_text(json.dumps(row))
                rows.append(row)
            (out / 'summary.json').write_text(json.dumps(dict(results=rows, payload_restored=True,
                manifest_sha256=stamp, qualified_phy=False, scope='diagnostic')))
            with patch.object(restore, 'context', return_value=manifest), \
                    patch.object(restore.baseline, 'completed_export'), \
                    patch.object(restore, 'payload', return_value=measurement) as measure:
                self.assertTrue(restore.verify(out)['payload_restored'])
                measure.return_value = {'payload_restored': False}
                with self.assertRaisesRegex(ValueError, 'remeasurement changed'):
                    restore.verify(out)
                measure.return_value = measurement
                (out / 'short/bench.raw').write_text('modified')
                with self.assertRaisesRegex(ValueError, 'unchanged complete'):
                    restore.verify(out)
