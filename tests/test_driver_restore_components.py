# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import hashlib
from contextlib import contextmanager
from threading import Barrier, Lock
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qualify_driver_restore_components as candidate
from driver_restore_variant import source_variant
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]


class DriverRestoreComponents(unittest.TestCase):
    def test_all_thirty_conditions_required_without_duplicates_or_mislabels(self):
        req = json.loads((ROOT / 'requirements.json').read_text())
        cases = candidate.cases(req)
        self.assertEqual(len(cases), 30)
        self.assertEqual(len(set(cases)), 30)
        tasks = [dict(id=f'{v}_driver_{p}_{t}', view=v, process=p, temperature=t) for v,p,t in cases]
        candidate.check_coverage(tasks, req)
        for bad in [tasks[:-1], tasks[:-1] + [tasks[0]], [dict(tasks[0], id='wrong')] + tasks[1:]]:
            with self.assertRaises(ValueError):
                candidate.check_coverage(bad, req)

    def test_source_fixture_preserves_bias_load_timing_and_only_selects_driver(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path(temp) / 'old';old.mkdir()
            source = (ROOT / 'analog/openlvds.spice').read_text()
            (old / 'source.spice').write_text(source)
            deck = (f'Title\n.include "{old}/source.spice"\n'
                    'XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver\n'
                    'RT P N 100\nCP P 0 2p\nCN N 0 2p\n'
                    'VD VDDD 0 1.8\n.tran 5p 2540n 0 1n\n'
                    '.print tran V(D) V(P) V(N) V(XD:XCORE:SINK) V(XD:XCORE:TOP) V(XD:XCORE:DP) V(XD:XCORE:DN)\n.end\n')
            (old / 'bench.cir').write_text(deck)
            selected = source_variant(source)
            body, result, stop = candidate.fixture(old, Path('/new'), selected, 'schematic')
            self.assertEqual(result.replace('/new/source.spice', str(old / 'source.spice')), deck)
            self.assertAlmostEqual(stop, 2540e-9, places=18)
            self.assertEqual(closure_hash(body, 'lvds_bias'), closure_hash(source, 'lvds_bias'))
            self.assertEqual(closure_hash(body, candidate.TOP), closure_hash(selected, candidate.TOP))
            with self.assertRaisesRegex(ValueError, 'native driver observation'):
                candidate.fixture(old, Path('/new'), selected, 'native')

    def test_incomplete_native_evidence_never_calls_the_simulation_producer(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(candidate.native, 'run') as run:
            root = Path(temp)
            for partial in [False, True]:
                if partial:
                    (root / 'summary.json').write_text(json.dumps(dict(diagnostic_complete=True)))
                with self.assertRaisesRegex(ValueError, 'must complete'):
                    candidate.native_ready(root)
                run.assert_not_called()
            for name in candidate.native.CASES:
                (root / name).mkdir();(root / name / 'summary.json').write_text('{}')
            (root / 'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,
                results=[dict(task='source_control'), dict(task='source_control')])))
            with self.assertRaisesRegex(ValueError, 'coverage'):
                candidate.native_ready(root)
            run.assert_not_called()
            (root / 'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,
                results=[dict(task=n) for n in candidate.native.CASES])))
            candidate.native_ready(root)
            run.assert_called_once_with(root)

    def test_voltage_eye_and_both_dc_polarities_are_required(self):
        wave = np.zeros((2, 9));wave[:, 1] = [0, 2540e-9]
        headers = {'TIME': 1, 'V(D)': 2, 'V(P)': 3, 'V(N)': 4}
        for eye, dc in [(True, True), (False, True), (True, False)]:
            with patch.object(candidate, 'driver_metrics', return_value=dict(passed=eye)) as rate, \
                 patch.object(candidate, 'driver_dc_metrics', return_value=dict(passed=dc)) as static:
                result = candidate.measurements(wave, headers, 2540e-9)
                self.assertEqual(result['passed'], eye and dc)
                self.assertEqual(result['loaded_eye_passed'], eye)
                rate.assert_called_once_with(wave);static.assert_called_once_with(wave)
        with patch.object(candidate, 'driver_metrics') as rate:
            for bad_wave, bad_header in [(wave[:1], headers), (wave[::-1], headers),
                                          (wave, dict(headers, **{'V(P)': 4}))]:
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    candidate.measurements(bad_wave, bad_header, 2540e-9)
            rate.assert_not_called()

    def test_parallel_failure_finishes_other_case_with_independent_leases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'requirements.json').write_text(json.dumps(dict(process_corners=['tt'], temperatures_c=[25])))
            layout = root / 'build/diagnostics/driver_layout/selected';layout.mkdir(parents=True)
            (layout / 'candidate.spice').write_text('model')
            (layout / 'extraction.json').write_text('{}')
            identity = dict(simulator_provenance='fixture', code={}, inputs={},
                            layout=str(layout.relative_to(root)), comparison='comparison')
            folder = root / 'build/diagnostics/driver_components' / hashlib.sha256(
                json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            folder.mkdir(parents=True)
            tasks = []
            for view in ['schematic', 'native']:
                name = f'{view}_driver_tt_25';case = folder / name;case.mkdir()
                (case / 'source.spice').write_text('body');(case / 'bench.cir').write_text('deck')
                tasks.append(dict(id=name, view=view, process='tt', temperature=25, stop_seconds=2540e-9,
                                  files={n:candidate.digest(case/n) for n in ['source.spice','bench.cir']}))
            (folder / 'manifest.json').write_text(json.dumps(dict(identity=identity, tasks=tasks)))
            barrier = Barrier(2);mutex = Lock();active = [];peak = [];exited = []
            @contextmanager
            def lease():
                with mutex:
                    active.append(1);peak.append(len(active))
                try:
                    yield
                finally:
                    with mutex:
                        active.pop();exited.append(1)
            def simulator(command, **kwargs):
                barrier.wait(timeout=10)
                case = kwargs['cwd']
                if case.name.startswith('schematic'):
                    (case / 'bench.cir.prn').write_text('wave')
                return candidate.subprocess.CompletedProcess(command, 1 if case.name.startswith('native') else 0,
                                                             stdout='', stderr='')
            with patch.object(candidate, 'ROOT', root), patch.object(candidate, 'provenance', return_value='fixture'), \
                 patch.object(candidate, 'fixture', return_value=('body','deck',2540e-9)), \
                 patch.object(candidate, 'checked_netlist', return_value='model'), \
                 patch.object(candidate, 'native_ready') as gate, patch.object(candidate, 'slot', lease), \
                 patch.object(candidate, 'command', return_value=['fixture']), \
                 patch.object(candidate.subprocess, 'run', side_effect=simulator), \
                 patch.object(candidate, 'read_wave', return_value=(None,None)), \
                 patch.object(candidate, 'measurements', return_value=dict(passed=True)):
                candidate.run(folder, 2)
                gate.assert_called_once_with(root / 'comparison')
            report = json.loads((folder / 'summary.json').read_text())
            self.assertFalse(report['passed']);self.assertEqual(report['passed_cases'], 1)
            self.assertEqual(len(report['results']), 2);self.assertEqual(max(peak), 2)
            self.assertEqual(active, []);self.assertEqual(len(exited), 2)
            self.assertEqual(json.loads((folder/'native_driver_tt_25/execution.json').read_text())['status'], 'held_for_diagnosis')
            self.assertEqual(json.loads((folder/'schematic_driver_tt_25/execution.json').read_text())['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
