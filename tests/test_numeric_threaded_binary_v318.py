# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_numeric_threaded_binary_v318 as runner


class NumericThreadRunnerTests(unittest.TestCase):
    def directory(self):
        (runner.ROOT / 'build').mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(dir=runner.ROOT / 'build')

    def test_startup_uses_numeric_set_and_rejects_other_types_or_counts(self):
        for threads in (1, 2):
            self.assertEqual(runner.startup_text(threads),
                f'set num_threads={threads}\necho OPENLVDS_NUMERIC_INIT_V318_{threads}\n')
        for threads in (0, 3, True, '1', 1.):
            with self.assertRaises(ValueError):
                runner.startup_text(threads)

    def test_command_keeps_batch_raw_log_and_omits_string_define_and_no_init(self):
        args = runner.command(Path('/loader'), Path('/library'), Path('/ngspice'),
                              Path('/bench.cir'), Path('/bench.raw'), Path('/ngspice.log'))
        self.assertEqual(args, ['/loader', '--library-path', '/library', '/ngspice',
                                '-b', '-r', '/bench.raw', '-o', '/ngspice.log', '/bench.cir'])
        self.assertNotIn('-D', args)
        self.assertNotIn('-n', args)

    def test_large_header_and_operating_point_do_not_count_as_transient(self):
        header = ('Title: ' + 'x' * 70000 + '\nFlags: real\nNo. Variables: 2\nNo. Points: 0\n'
                  'Variables:\n 0 time time\n 1 v(out) voltage\nBinary:\n').encode()
        with self.directory() as directory:
            raw = Path(directory) / 'bench.raw'
            for body, expected in ((b'', False), (struct.pack('<dd', 0, 0), False),
                    (struct.pack('<dddd', 0, 0, 0, 0), False),
                    (struct.pack('<dddd', 0, 0, 1e-12, 1.8), True),
                    (struct.pack('<ddd', 0, 0, 1e-12), False)):
                raw.write_bytes(header + body)
                self.assertEqual(runner.active_progress(raw), expected)

    def test_observation_errors_and_timeouts_do_not_stop_the_child(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired('ngspice', .25), ('output', '')]
        with patch.object(Path, 'iterdir', side_effect=OSError('transient observer error')):
            out, err, samples, active = runner.observe(process, Path('/missing/raw'))
        self.assertEqual((out, err, samples, active), ('output', '', {}, {}))
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_actual_private_initialization_for_both_counts_without_simulation(self):
        if not (runner.ROOT / 'build/tools/ngspice.json').exists():
            self.skipTest('Requires pinned ngspice runtime for frontend-only check')
        with self.directory() as directory:
            for threads in (1, 2):
                folder = Path(directory) / str(threads)
                report = runner.startup_check(folder, threads)
                self.assertTrue(report['private_startup_loaded'])
                self.assertTrue(report['frontend_only'])
                self.assertTrue(report['no_native_analysis_performed'])
                self.assertFalse(report['native_transient_validated'])
                self.assertFalse(report['active_thread_configuration_observed'])
                self.assertFalse(report['backend_admitted'])
                self.assertFalse(list(folder.glob('*.raw')))
                self.assertNotIn('.tran', (folder / 'frontend.cir').read_text())

    def test_existing_partial_native_artifacts_are_retained_before_execution(self):
        with self.directory() as directory:
            folder = Path(directory); deck = folder / 'bench.cir'
            deck.write_text('original\n.tran 1p 25n\n.end\n')
            raw = deck.with_suffix('.raw'); raw.write_bytes(b'preserved partial')
            with patch.object(runner, 'runtime') as runtime:
                with self.assertRaisesRegex(ValueError, 'Retain prior'):
                    runner.run(deck, folder / 'ngspice.log', 1)
                runtime.assert_not_called()
            self.assertEqual(raw.read_bytes(), b'preserved partial')

    def test_runtime_records_private_init_and_exact_original_translation(self):
        with self.directory() as directory:
            folder = Path(directory); deck = folder / 'bench.cir'
            deck.write_text('original\n.tran 1p 25n\n.end\n')
            process = Mock(returncode=0, pid=12345)
            def observed(child, raw):
                raw.write_bytes(b'raw fixture')
                return 'OPENLVDS_NUMERIC_INIT_V318_1\n', '', {1: 3}, {1: 2}
            translated = 'byte identical original translation\n.end\n'
            with patch.object(runner.original, 'translate', return_value=(translated, ['v(out)'])), \
                 patch.object(runner, 'runtime', return_value=(Path('/loader'), Path('/library'), Path('/ngspice'))), \
                 patch.object(runner.subprocess, 'Popen', return_value=process) as popen, \
                 patch.object(runner, 'observe', side_effect=observed), \
                 patch.object(runner.original, 'validate') as validate:
                self.assertEqual(runner.run(deck, folder / 'ngspice.log', 1), 0)
            validate.assert_called_once()
            self.assertEqual(deck.with_suffix('.ngspice.cir').read_text(), translated)
            self.assertEqual(popen.call_args.kwargs['env']['SPICE_USERINIT_DIR'], str(folder / runner.INIT_DIRECTORY))
            report = json.loads((folder / 'runtime.json').read_text())
            for field in ('native_transient_validated', 'private_numeric_thread_init_loaded',
                          'private_numeric_thread_init_unchanged', 'original_deck_translation_retained',
                          'active_thread_configuration_observed'):
                self.assertTrue(report[field])
            self.assertFalse(report['models_or_tolerances_changed'])
            self.assertFalse(report['backend_admitted'])

    def test_lost_startup_file_retains_runtime_receipt_and_native_artifacts(self):
        with self.directory() as directory:
            folder = Path(directory); deck = folder / 'bench.cir'
            deck.write_text('original\n.tran 1p 25n\n.end\n')
            process = Mock(returncode=0, pid=12345)
            def observed(child, raw):
                raw.write_bytes(b'raw fixture')
                (folder / runner.INIT_DIRECTORY / '.spiceinit').unlink()
                return 'OPENLVDS_NUMERIC_INIT_V318_1\n', '', {1: 2}, {1: 1}
            with patch.object(runner.original, 'translate', return_value=('translated', ['v(out)'])), \
                 patch.object(runner, 'runtime', return_value=(Path('/loader'), Path('/library'), Path('/ngspice'))), \
                 patch.object(runner.subprocess, 'Popen', return_value=process), \
                 patch.object(runner, 'observe', side_effect=observed), patch.object(runner.original, 'validate'):
                with self.assertRaisesRegex(ValueError, 'startup did not remain verified'):
                    runner.run(deck, folder / 'ngspice.log', 1)
            report = json.loads((folder / 'runtime.json').read_text())
            self.assertTrue(report['native_transient_validated'])
            self.assertFalse(report['private_numeric_thread_init_unchanged'])
            self.assertEqual(deck.with_suffix('.raw').read_bytes(), b'raw fixture')


if __name__ == '__main__':
    unittest.main()
