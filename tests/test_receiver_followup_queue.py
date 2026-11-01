# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import queue_receiver_followup as queue
from queue_receiver_followup import completed_native, producer_names


class ReceiverFollowupQueue(unittest.TestCase):
    def test_active_owner_never_releases_or_reads_incomplete_artifacts(self):
        self.assertIsNone(completed_native({'status': 'run_replay'}, True))

    def test_terminal_failure_and_incomplete_state_hold(self):
        for status in ['held_for_diagnosis', 'run_replay', 'waiting_for_source_comparison']:
            with self.assertRaisesRegex(ValueError, 'did not pass'):
                completed_native({'status': status}, False)

    def test_native_selection_and_actual_edge_reports_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            layout = root / 'build/diagnostics/receiver_layout/selected'
            replay = root / 'build/diagnostics/receiver_replay/selected'
            replay.mkdir(parents=True)
            state = dict(status='native_replay_passed', layout=str(layout.relative_to(root)),
                         replay=str(replay.relative_to(root)))
            manifest = replay / 'manifest.json'
            manifest.write_text(json.dumps(dict(identity=dict(layout=state['layout']))))
            summary = dict(diagnostic_complete=True, results=[dict(task=n, receiver_transport=dict(
                missing_output_edges=0, pulses=[dict(output_edges_in_next_input_period=1)]))
                for n in ['captured', 'sharp_control']])
            report = replay / 'summary.json'
            report.write_text(json.dumps(summary))
            self.assertEqual(completed_native(state, False, root), (layout, replay))
            for count in [0, 2]:
                summary['results'][0]['receiver_transport']['pulses'][0]['output_edges_in_next_input_period'] = count
                report.write_text(json.dumps(summary))
                with self.assertRaisesRegex(ValueError, 'clock edges'):
                    completed_native(state, False, root)
            manifest.write_text(json.dumps(dict(identity=dict(layout='other'))))
            with self.assertRaisesRegex(ValueError, 'different receiver'):
                completed_native(state, False, root)
            state['replay'] = '../outside'
            with self.assertRaisesRegex(ValueError, 'Unexpected receiver artifact'):
                completed_native(state, False, root)

    def test_host_can_capture_both_scientific_producer_sets_without_numpy(self):
        names = producer_names()
        self.assertTrue({'qualify_receiver_components.py', 'probe_receiver_fast_restore_candidate.py',
                         'run_ngspice.py', 'continue_receiver_candidate.py'} <= names)

    def test_tail_profile_captures_selected_verifier_and_dispatches_exact_selector(self):
        names = producer_names(profile='unclamped_tail_headroom')
        self.assertTrue({'qualify_unclamped_receiver.py', 'continue_receiver_unclamped_candidate.py',
                         'probe_receiver_tail_headroom_candidate.py', 'receiver_tail_timestep_retry.py',
                         'receiver_tail_headroom_matrix.py', 'layout_receiver_tail_headroom_candidate.py'} <= names)
        commands = queue.preparation_commands('unclamped_tail_headroom', Path('layout'), Path('replay'), Path('link'))
        self.assertEqual(commands, (
            ['scripts/qualify_unclamped_receiver.py', 'prepare-components', 'layout', '--replay', 'replay'],
            ['scripts/qualify_unclamped_receiver.py', 'prepare-link', 'link', '--replay', 'replay'],
            'scripts/continue_receiver_unclamped_candidate.py'))
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            queue.preparation_commands('unexpected', Path('layout'), Path('replay'), Path('link'))

    def test_container_paths_map_to_host_with_kind_and_traversal_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            relative = Path('build/diagnostics/receiver_components/selected')
            for value in [relative, root / relative, Path('/work/OpenLVDS') / relative]:
                self.assertEqual(queue_artifact(value, 'receiver_components', root), root / relative)
            for value in ['/work/OpenLVDS/build/diagnostics/receiver_replay/other',
                          '/work/OpenLVDS/build/diagnostics/receiver_components/../../outside',
                          '/work/OpenLVDS-other/build/diagnostics/receiver_components/selected']:
                with self.assertRaisesRegex(ValueError, 'Unexpected receiver artifact'):
                    queue_artifact(value, 'receiver_components', root)

    def test_queue_waits_then_prepares_and_checks_both_child_reports(self):
        for native_passes, profile, replay_profile in [
                (False, 'baseline', 'baseline'), (True, 'baseline', 'baseline'),
                (False, 'unclamped_tail_headroom', 'unclamped_tail_headroom'),
                (True, 'unclamped_tail_headroom', 'unclamped_tail_headroom'),
                (True, 'unclamped_tail_headroom', 'unclamped_fast_restore')]:
            with self.subTest(native_passes=native_passes, profile=profile), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                screen = root / 'build/diagnostics/receiver_clamp/source'
                upstream = screen / 'native_continuation'
                upstream.mkdir(parents=True)
                (upstream / 'manifest.json').write_text(json.dumps(dict(code={})))
                (screen / 'manifest.json').write_text('{}')
                (upstream / 'state.json').write_text(json.dumps(dict(status='held_for_diagnosis')))
                (root / 'requirements.json').write_text('{}')
                (root / 'scripts').mkdir()
                (root / 'scripts/env.sh').write_text('fixture')
                link = root / 'build/link/original'
                link.mkdir(parents=True)
                for name in ['summary.json', 'bench.cir', 'library.spice', 'bench.cir.prn']:
                    (link / name).write_text('fixture')
                layout = root / 'build/diagnostics/receiver_layout/selected'
                replay = root / 'build/diagnostics/receiver_replay/selected'
                replay.mkdir(parents=True)
                (replay / 'manifest.json').write_text(json.dumps(dict(identity=dict(clamp_variant=replay_profile))))
                components = root / 'build/diagnostics/receiver_components/selected'
                candidate_link = root / 'build/diagnostics/receiver_candidate_link/selected'
                calls = []

                def child(command, **kwargs):
                    calls.append(command)
                    if command[0] == 'systemctl':
                        return queue.subprocess.CompletedProcess(command, 0,
                            stdout='active\n' if len(calls) == 1 else 'inactive\n')
                    self.assertGreaterEqual(len(calls), 3)
                    if any(value.startswith('prepare') for value in command):
                        tail = profile == 'unclamped_tail_headroom'
                        component_command = ('prepare-components' in command if tail else
                                             'scripts/qualify_receiver_components.py' in command)
                        self.assertTrue(all(not Path(value).is_absolute() for value in command[-2:]))
                        self.assertEqual(command[-1], str(replay.relative_to(root)))
                        self.assertEqual(command[-3] if tail else command[-2],
                                         str((layout if component_command else link).relative_to(root)))
                        path = components if component_command else candidate_link
                        path.mkdir(parents=True)
                        (path / 'manifest.json').write_text('{}')
                        kwargs['stdout'].write(str(Path('/work/OpenLVDS') / path.relative_to(root)) + '\n')
                    else:
                        for path in [components, candidate_link]:
                            (path / 'summary.json').write_text(json.dumps(dict(
                                passed=True, manifest_sha256=queue.digest(path / 'manifest.json'))))
                        kwargs['stdout'].write('followup complete\n')
                    return queue.subprocess.CompletedProcess(command, 0)

                with patch.object(queue, 'ROOT', root), patch.object(queue, 'artifact',
                        side_effect=lambda value, kind: queue_artifact(value, kind, root)), \
                     patch.object(queue, 'producer_names', return_value=set()), \
                     patch.object(queue, 'completed_native', side_effect=[None, (layout, replay)] if native_passes
                                  else [None, ValueError('Native receiver continuation did not pass')]), \
                     patch.object(queue.subprocess, 'run', side_effect=child), patch.object(queue.time, 'sleep'):
                    succeeds = native_passes and profile == replay_profile
                    if succeeds:
                        queue.run(screen, link, 'fixture.service', profile)
                    else:
                        with self.assertRaisesRegex(ValueError, 'did not pass' if not native_passes else 'requested receiver profile'):
                            queue.run(screen, link, 'fixture.service', profile)
                saved = json.loads((screen / 'component_link_continuation/state.json').read_text())
                self.assertFalse(saved['qualified_phy'])
                self.assertEqual(saved['status'], 'diagnostics_passed' if succeeds else 'held_for_diagnosis')
                self.assertEqual(len(calls), 5 if succeeds else 2)


queue_artifact = queue.artifact


if __name__ == '__main__':
    unittest.main()
