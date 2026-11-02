# SPDX-License-Identifier: GPL-3.0-only
from contextlib import ExitStack
import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_driver_shape_source as admission

ROOT = Path(__file__).resolve().parents[1]
METRICS = dict(common_mode_pp_v=.12, rising_output_edges=22,
    mean_supply_power_w=dict(io=.026, digital=.0012),
    added_mos_stress=[dict(max_abs_vgs=4.04, max_abs_vgd=4., max_abs_vds=3.4, max_abs_vbs=0.)])
EDGES = dict(within_reference=True)


def dc(path):
    return dict(differential_v=-.34 if 'negative_op' in str(path) else .34,
                common_mode_v=1.25, differential_pp_v=0., common_mode_pp_v=0.)


class FullSourceVerification(unittest.TestCase):
    def fixture(self, root):
        req = json.loads((ROOT / 'requirements.json').read_text())
        (root / 'requirements.json').write_text(json.dumps(req))
        identity = dict(inputs={}, code={}, simulator='engine')
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        out = root / 'build/diagnostics/driver_shape_source' / fingerprint
        out.mkdir(parents=True)
        tasks = admission.source.cases(req)
        for task in tasks:
            folder = out / task['id']
            folder.mkdir()
            for name in ['source.spice', 'bench.cir', 'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log']:
                (folder / name).write_text(name)
            task['files'] = {name: admission.sha(folder / name) for name in ['source.spice', 'bench.cir']}
        (out / 'manifest.json').write_text(json.dumps(dict(identity=identity, tasks=tasks)))
        stamp = admission.sha(out / 'manifest.json')
        results = []
        for task in tasks:
            folder = out / task['id']
            row = dict(case=task['id'], task=task['op'], returncode=0, error=None,
                       manifest_sha256=stamp, metrics=METRICS, initial_dc=dc(folder),
                       files={name: admission.sha(folder / name) for name in
                              ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log']})
            (folder / 'summary.json').write_text(json.dumps(row))
            results.append(row)
        points = [dict(process=p, temperature=t, passed=True, error=None,
                       calibrated_transitions={op: EDGES for op in admission.source.shape.CASES})
                  for p, t in itertools.product(req['process_corners'], req['temperatures_c'])]
        (out / 'summary.json').write_text(json.dumps(dict(source_waveform_matrix_passed=True,
            required_cases=30, required_pvt=15, passed_pvt=15, manifest_sha256=stamp,
            results=results, pvt=points)))
        return out, tasks

    def mocks(self, root):
        stack = ExitStack()
        stack.enter_context(patch.object(admission, 'ROOT', root))
        stack.enter_context(patch.object(admission.source, 'provenance', return_value='engine'))
        stack.enter_context(patch.object(admission.source.shape, 'read_wave', side_effect=lambda p: (p, None)))
        stack.enter_context(patch.object(admission.source.shape, 'initial_dc', side_effect=lambda p, h: dc(p)))
        stack.enter_context(patch.object(admission.source.shape, 'transitions', return_value=EDGES))
        measure = stack.enter_context(patch.object(admission.source.shape.pilot, 'measure', return_value=METRICS))
        return stack, measure

    def test_remeasures_all_thirty_and_does_not_claim_physical_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, _ = self.fixture(root)
            before = (out / 'summary.json').read_bytes()
            stack, measure = self.mocks(root)
            with stack:
                report = admission.verify(out)
            self.assertEqual(measure.call_count, 30)
            self.assertTrue(report['source_waveform_ready'])
            self.assertFalse(report['physical_admission'])
            self.assertFalse(report['qualified_phy'])
            self.assertEqual(report['maximum_added_device_terminal_difference_v'], 4.04)
            self.assertEqual((out / 'summary.json').read_bytes(), before)

    def test_partial_campaign_never_invokes_measurement_or_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, tasks = self.fixture(root)
            (out / tasks[-1]['id'] / 'summary.json').unlink()
            stack, measure = self.mocks(root)
            with stack, self.assertRaisesRegex(ValueError, 'Complete all thirty'):
                admission.verify(out)
            measure.assert_not_called()

    def test_changed_waveform_and_false_aggregate_are_rejected(self):
        for mutation in ['waveform', 'aggregate', 'measurement']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out, tasks = self.fixture(root)
                if mutation == 'waveform':
                    (out / tasks[0]['id'] / 'bench.raw').write_text('changed')
                elif mutation == 'aggregate':
                    path = out / 'summary.json'
                    row = json.loads(path.read_text())
                    row['pvt'][-1]['calibrated_transitions']['positive_op'] = dict(within_reference=False)
                    path.write_text(json.dumps(row))
                stack, measure = self.mocks(root)
                with stack:
                    if mutation == 'measurement':
                        measure.return_value = dict(METRICS, common_mode_pp_v=.151)
                    with self.assertRaises(ValueError):
                        admission.verify(out)

    def test_all_pass_claim_cannot_hide_failed_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, tasks = self.fixture(root)
            path = out / tasks[-1]['id'] / 'summary.json'
            row = json.loads(path.read_text())
            row['returncode'] = 1
            path.write_text(json.dumps(row))
            stack, _ = self.mocks(root)
            with stack, self.assertRaisesRegex(ValueError, 'incomplete or failed'):
                admission.verify(out)


if __name__ == '__main__':
    unittest.main()
