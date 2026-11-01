# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import itertools
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qualify_selected_analog_link as selected


class SelectedAnalogLink(unittest.TestCase):
    def test_failed_reference_can_prepare_matched_pair_after_both_cached_suites_pass(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
            root = Path(tmp)
            paths = {name: root / 'build/diagnostics' / name / 'example' for name in
                     ['driver_components', 'receiver_components', 'receiver_candidate_link', 'driver_native_restore']}
            for path in paths.values():
                path.mkdir(parents=True); (path / 'manifest.json').write_text('{}'); (path / 'summary.json').write_text('{}')
            (root / 'requirements.json').write_text('{}'); (root / 'scripts').mkdir()
            (root / 'scripts' / selected.NAME).write_text('producer fixture')
            comparison = root / 'build/diagnostics/driver_native_restore/original'; comparison.mkdir()
            (comparison / 'manifest.json').write_text(json.dumps(dict(identity=dict(layouts=dict(
                source_control='control', restore_64_24='candidate')))))
            d = dict(identity=dict(variant='restore_64_24', comparison=str(comparison.relative_to(root)), layout='candidate', code={}, inputs={}), tasks=[])
            r = dict(identity=dict(replay='replay', layout='receiver', code={}, inputs={}), tasks=[])
            link = paths['receiver_candidate_link']
            (link / 'manifest.json').write_text(json.dumps(dict(identity=dict(replay='replay', receiver='receiver'))))
            (link / 'summary.json').write_text(json.dumps(dict(passed=False, manifest_sha256=selected.native.digest(link / 'manifest.json'))))
            out = paths['driver_native_restore']
            with patch.object(selected, 'complete_components', side_effect=[d, r, d, r]), patch.object(selected.selected, 'selected_replay'), patch.object(selected.driver, 'run') as driver, patch.object(selected.selected, 'run') as receiver, patch.object(selected.native, 'prepare', return_value=out) as prepare:
                self.assertEqual(selected.prepare(paths['driver_components'], paths['receiver_components'], link), out)
                driver.assert_called_once_with(paths['driver_components'], 1)
                self.assertEqual(receiver.call_args_list[0].args, ('run-components', paths['receiver_components']))
                self.assertEqual(receiver.call_args_list[1].args, ('run-link', link))
                prepare.assert_called_once_with(link, root / 'control', root / 'candidate')
            admission = json.loads((out / 'selected_analog_admission.json').read_text())
            self.assertFalse(admission['receiver_reference_link_passed']); self.assertFalse(admission['qualified_phy'])

    def test_incomplete_real_driver_campaign_cannot_call_any_simulator(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
            root = Path(tmp); (root / 'requirements.json').write_text(json.dumps(dict(
                process_corners=['tt', 'ff', 'ss', 'fs', 'sf'], temperatures_c=[0, 25, 40])))
            folder = root / 'build/diagnostics/driver_components/example'; folder.mkdir(parents=True)
            tasks = [dict(id=f'{v}_driver_{p}_{t}', view=v, process=p, temperature=t)
                     for v, p, t in itertools.product(['schematic', 'native'], ['tt', 'ff', 'ss', 'fs', 'sf'], [0, 25, 40])]
            (folder / 'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
            with patch.object(selected.driver, 'run') as driver, patch.object(selected.selected, 'run') as receiver, patch.object(selected.native, 'prepare') as prepare:
                with self.assertRaisesRegex(ValueError, 'Complete all selected driver'): selected.prepare(folder, root / 'unused', root / 'unused')
                driver.assert_not_called(); receiver.assert_not_called(); prepare.assert_not_called()

    def test_receiver_mismatch_refuses_before_cached_producer_calls(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
            root = Path(tmp); link = root / 'build/diagnostics/receiver_candidate_link/example'; link.mkdir(parents=True)
            (link / 'manifest.json').write_text(json.dumps(dict(identity=dict(replay='wrong', receiver='wrong'))))
            (link / 'summary.json').write_text('{}')
            manifests = [dict(identity=dict(variant='restore_64_24')), dict(identity=dict(replay='selected', layout='selected'))]
            with patch.object(selected, 'complete_components', side_effect=manifests), patch.object(selected.driver, 'run') as driver, patch.object(selected.native, 'prepare') as prepare:
                with self.assertRaisesRegex(ValueError, 'different receivers'): selected.prepare(root, root, link)
                driver.assert_not_called(); prepare.assert_not_called()

    def run_fixture(self, root, decoder=True, sensitivity=.11):
        folder = root / 'build/diagnostics/driver_native_restore/example'; folder.mkdir(parents=True)
        (root / 'requirements.json').write_text(json.dumps(dict(rx_threshold_v=.1)))
        (folder / 'manifest.json').write_text('{}')
        (folder / 'selected_analog_admission.json').write_text(json.dumps(dict(
            comparison_manifest_sha256=selected.native.digest(folder / 'manifest.json'), inputs={
                'requirements.json': selected.native.digest(root / 'requirements.json')})))
        results = [dict(task='source_control', decoder=dict(passed=False)),
                   dict(task='restore_64_24', decoder=dict(passed=decoder, sampling_margin_passed=decoder),
                        clock_centers={name: dict(min_center_abs_v=sensitivity, below_rx_threshold=int(sensitivity < .1))
                                       for name in ['tx_clock', 'rx_clock']})]
        for case in selected.native.CASES:
            child = folder / case; child.mkdir(); (child / 'summary.json').write_text('{}')
        (folder / 'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,
            manifest_sha256=selected.native.digest(folder / 'manifest.json'), results=results)))
        return folder

    def test_candidate_pass_is_independent_of_expected_failed_control(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
            folder = self.run_fixture(Path(tmp))
            with patch.object(selected.native, 'run') as run:
                result = json.loads(selected.run(folder).read_text()); run.assert_called_once_with(folder)
            self.assertTrue(result['selected_link_passed']); self.assertFalse(result['qualified_phy'])

    def test_successful_owner_cannot_override_decoder_or_sensitivity_failure(self):
        for decoder, sensitivity in [(False, .11), (True, .09)]:
            with self.subTest(decoder=decoder), tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
                folder = self.run_fixture(Path(tmp), decoder, sensitivity)
                with patch.object(selected.native, 'run', return_value=None): result = json.loads(selected.run(folder).read_text())
                self.assertFalse(result['selected_link_passed'])

    def test_partial_trace_is_preserved_without_simulation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
            folder = self.run_fixture(Path(tmp)); child = folder / 'restore_64_24'
            (child / 'summary.json').unlink(); raw = child / 'bench.raw'; raw.write_bytes(b'partial')
            with patch.object(selected.native, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Partial'): selected.run(folder)
                run.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'partial')

    def test_changed_admission_inputs_refuse_before_native_execution(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(selected, 'ROOT', Path(tmp)):
            folder = self.run_fixture(Path(tmp)); (Path(tmp) / 'requirements.json').write_text('{}')
            with patch.object(selected.native, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'admission changed'): selected.run(folder)
                run.assert_not_called()


if __name__ == '__main__': unittest.main()
