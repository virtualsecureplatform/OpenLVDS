import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_rx_clock_skew as probe


class ReceiveClockSkew(unittest.TestCase):
    def test_only_four_declared_circuits_and_one_geometry_change(self):
        self.assertEqual(list(probe.policy.VARIANTS), ['n042', 'n065', 'n084', 'n100'])
        for name, width in probe.policy.VARIANTS.items():
            text, devices = probe.policy.circuit(name)
            self.assertEqual(len(devices), 4)
            self.assertEqual([(d['name'], d['width_um']) for d in devices], [('XP0', 4), ('XN0', width), ('XP1', 16), ('XN1', 8)])
            self.assertIn('.subckt ' + probe.policy.TOP + ' IN OUT VDDD VSS', text)
            self.assertTrue(all(d['length_um'] == .15 for d in devices))
            self.assertNotIn('IREF', text)
        with self.assertRaises(ValueError): probe.policy.circuit('unbounded')

    def test_fixture_changes_only_receive_clock_path_and_stop(self):
        old = ('original\n.include "/parent/payload/library.spice"\n'
            'XCR RCP RCN RXCLOCK VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core\n'
            'XRX 0 VDDD RXCLOCK Q0 Q1 RESET_N RXDATA RXVALID openlvds_ddr_rx\n'
            'RRET source load 100\n.tran 1p 188.049n 0 1p\n.print tran V(RXDATA) V(RXCLOCK)\n.end\n')
        new = probe.fixture(old, Path('/parent'), Path('/out'), 'n042')
        restored = new.replace('/out/n042.spice', '/parent/payload/library.spice').replace('RXCLOCK_RAW', 'RXCLOCK')
        restored = restored.replace('XSH RXCLOCK RXCLOCK VDDD 0 ' + probe.policy.TOP + '\n', '')
        restored = restored.replace('.tran 1p 120n 0 1p', '.tran 1p 188.049n 0 1p')
        restored = restored.replace(' V(RXCLOCK) V(XSH:MID) V(VDDD)', '')
        self.assertEqual(restored, old)
        with self.assertRaises(ValueError): probe.fixture(old.replace('.tran 1p', '.tran 10p'), Path('/parent'), Path('/out'), 'n042')

    def test_missing_complete_aperture_cannot_create_source_artifact(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'parent'; (parent / 'payload').mkdir(parents=True)
            (parent / 'manifest.json').write_text('{}'); (parent / 'payload/library.spice').write_text('native circuit')
            with patch.object(probe, 'ROOT', root), patch.object(probe.coupled, 'verify', return_value=dict(payload_restored=True)), \
                 patch.object(probe, 'aperture_gate', side_effect=ValueError('incomplete aperture')):
                with self.assertRaisesRegex(ValueError, 'incomplete aperture'): probe.prepare(parent, root / 'aperture')
                self.assertFalse((root / 'build/diagnostics' / probe.NAMESPACE).exists())

    def test_another_capture_model_is_rejected_before_reading_an_aperture(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); folder = root / 'build/characterization/rx_aperture/test'; folder.mkdir(parents=True)
            (folder / 'manifest.json').write_text('{}'); (folder / 'library.spice').write_text('different circuit')
            with patch.object(probe, 'ROOT', root), patch.object(probe.aperture, 'validate'), \
                 patch.object(probe, 'closure_hash', side_effect=['native', 'different']), patch.object(probe.evidence, 'read_table') as read:
                with self.assertRaises(ValueError): probe.aperture_gate(folder, 'native circuit')
                read.assert_not_called()

    def test_payload_slew_aperture_margins_and_all_mos_stresses_are_mandatory(self):
        t = np.linspace(0, 120e-9, 1201); clock = 1.8 * ((t % 2.5e-9) < 1.25e-9)
        wave = np.column_stack([np.arange(len(t)), t, clock, clock, clock, np.full(len(t), .9), np.full(len(t), 1.8)])
        h = {f'V({n})': i + 2 for i, n in enumerate(['CLK0', 'RXCLOCK_RAW', 'RXCLOCK', 'XSH:MID', 'VDDD'])}
        receipt = dict(qualified=True, setup_ps=270, hold_ps=110, input_slew_ps=[20, 200])
        metrics = dict(passed=True, checked_bits=32, word_errors=0, capture_aperture_slew_passed=True, setup_margin_ps=210, hold_margin_ps=220)
        with patch.object(probe.coupled.baseline, 'completed_export', return_value=(wave, h)), \
             patch.object(probe.coupled.baseline.original, 'analyze', return_value=metrics) as analyze:
            result = probe.measure(Path('fixture'), dict(id='n042'), receipt)
            self.assertTrue(result['passed']); self.assertEqual(len(result['stress']), 4)
            self.assertEqual(analyze.call_args.kwargs['aperture'], receipt)
            for key, value in [('passed', False), ('checked_bits', 30), ('word_errors', 1),
                               ('capture_aperture_slew_passed', False), ('setup_margin_ps', 199), ('hold_margin_ps', 199)]:
                changed = dict(metrics); changed[key] = value; analyze.return_value = changed
                self.assertFalse(probe.measure(Path('fixture'), dict(id='n042'), receipt)['passed'])
            analyze.return_value = metrics; changed = wave.copy(); changed[0, h['V(XSH:MID)']] = 2.0
            with patch.object(probe.coupled.baseline, 'completed_export', return_value=(changed, h)):
                self.assertFalse(probe.measure(Path('fixture'), dict(id='n042'), receipt)['passed'])

    def test_ranking_uses_both_margins_and_never_grants_phy_admission(self):
        m = dict(identity=dict(scope='source only'), tasks=[dict(id=v) for v in probe.policy.VARIANTS])
        rows = [dict(variant=v, error=None, result=dict(passed=True, payload=dict(setup_margin_ps=210+i*10, hold_margin_ps=240-i*10)))
                for i, v in enumerate(probe.policy.VARIANTS)]
        report = probe.aggregate(m, rows)
        self.assertEqual(report['ranked_survivors'][0], 'n065')
        self.assertFalse(report['qualified_phy']); self.assertFalse(report['physical_admission'])
        with self.assertRaises(ValueError): probe.aggregate(m, rows[:-1])
        with self.assertRaises(ValueError): probe.aggregate(m, rows[:-1] + [rows[0]])
        changed = copy.deepcopy(rows); changed[0]['error'] = 'numerical failure'
        self.assertNotIn('n042', probe.aggregate(m, changed)['ranked_survivors'])

    def test_partial_output_is_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'manifest.json').write_text('{}'); (root / 'state.json').write_text('{}')
            with patch.object(probe, 'bound', return_value={}), patch.object(probe, 'command') as command:
                with self.assertRaisesRegex(ValueError, 'no retry'): probe.run(root)
                command.assert_not_called()
