import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qualify_analog_frontend_controls as controls


class AnalogFrontendControls(unittest.TestCase):
    def source(self, worst=('ss', 40)):
        req = json.loads((controls.ROOT / 'requirements.json').read_text())
        tasks = controls.expansion.tasks(req, 'tail140_w20')
        manifest = dict(identity=dict(variant='tail140_w20'), tasks=tasks)
        rows = [dict(task=t['id'], variant=t['variant'], spec=t['spec'], error=None,
                     result=dict(passed=True, native_phase=dict(phase=dict(filtered_area_difference_v=t['spec']['offset_ps'] / 1000)))) for t in tasks]
        report = dict(analog_source_expansion_passed=True, variant='tail140_w20', worst_screened_pvt=list(worst), results=rows)
        return report, manifest

    def test_control_coverage_preserves_all_pvt_and_worst_corner_frequencies(self):
        for worst, count in [(('ss', 40), 57), (('tt', 0), 63)]:
            report, manifest = self.source(worst); tasks = controls.task_plan(report, manifest)
            self.assertEqual(len(tasks), count); self.assertEqual(len({t['id'] for t in tasks}), count)
            self.assertTrue(all(t['spec']['offset_ps'] == 0 and t['area_limits_v'] == [-.02, .02] for t in tasks))
            points = {(t['spec']['process'], t['spec']['temperature']) for t in tasks if t['spec']['mhz'] == 400}
            self.assertEqual(len(points), 15)
            for p, temp in {('ss', 40), ('tt', 25), worst}:
                self.assertEqual({t['spec']['mhz'] for t in tasks if (t['spec']['process'], t['spec']['temperature']) == (p, temp)}, {390, 400, 410})

    def test_partial_false_and_duplicate_source_results_cannot_admit_controls(self):
        report, manifest = self.source()
        for changed in (dict(report, analog_source_expansion_passed=False), dict(report, results=report['results'][:-1]),
                        dict(report, results=report['results'][:-1] + [report['results'][0]])):
            with self.assertRaises(ValueError): controls.task_plan(changed, manifest)
        changed = copy.deepcopy(report)
        task = controls.task_plan(report, manifest)[0]
        donor = next(r for r in changed['results'] if r['task'] == task['donor'])
        donor['result']['passed'] = False
        with self.assertRaises(ValueError): controls.task_plan(changed, manifest)

    def test_a_zero_bracket_cannot_be_inferred_from_one_sided_recovery(self):
        report, manifest = self.source()
        for row in report['results']:
            if row['spec']['offset_ps'] == -20:
                row['result']['native_phase']['phase']['filtered_area_difference_v'] = .001
        with self.assertRaisesRegex(ValueError, 'zero bracket'): controls.task_plan(report, manifest)

    def test_missing_source_admission_creates_no_control_artifact(self):
        with tempfile.TemporaryDirectory() as name, patch.object(controls, 'admission', side_effect=ValueError('source incomplete')):
            root = Path(name)
            with self.assertRaises(ValueError): controls.prepare(root / 'source')
            self.assertEqual(list(root.iterdir()), [])

    def test_recovery_protocol_keeps_analog_health_and_all_eight_clocks(self):
        aliases = {n: n for n in ('REF', 'FDB', 'REF_FAST', 'FDB_FAST', 'REF_FF_CLK_0', 'REF_FF_CLK_1',
                                  'FB_FF_CLK_0', 'FB_FF_CLK_1', 'RST', 'ENABLE')}
        header = {'V(' + n + ')': i + 2 for i, n in enumerate(aliases)}
        wave = np.zeros((3, len(aliases) + 2))
        phase = dict(passed=True, native_phase=dict(phase=dict(filtered_area_difference_v=.001)))
        task = dict(spec=dict(mhz=400), aliases=aliases, area_limits_v=[-.02, .02])
        with patch.object(controls.expansion, 'measure', return_value=phase) as measured, \
             patch.object(controls.expansion.screen.original.pilot.original, 'completed', return_value=(wave, header)), \
             patch.object(controls.protocol, 'measure', return_value=dict(passed=True)) as protocol:
            self.assertTrue(controls.measure(Path('case'), task)['passed'])
            self.assertEqual(len(protocol.call_args.args[-1]), 8)
            for area in (-.021, .021, float('nan')):
                phase['native_phase']['phase']['filtered_area_difference_v'] = area
                self.assertFalse(controls.measure(Path('case'), task)['passed'])
            phase['native_phase']['phase']['filtered_area_difference_v'] = 0
            phase['passed'] = False
            self.assertFalse(controls.measure(Path('case'), task)['passed'])
            phase['passed'] = True; protocol.return_value = dict(passed=False)
            self.assertFalse(controls.measure(Path('case'), task)['passed'])

    def test_control_failure_or_missing_results_never_grants_physical_admission(self):
        source, manifest = self.source(); pending = controls.task_plan(source, manifest)
        m = dict(identity=dict(variant='tail140_w20', scope='source controls'), tasks=pending)
        rows = [dict(task=t['id'], variant=t['variant'], spec=t['spec'], error=None, result=dict(passed=True)) for t in pending]
        result = controls.aggregate(m, rows)
        self.assertTrue(result['analog_source_controls_passed']); self.assertFalse(result['qualified_phy']); self.assertFalse(result['physical_admission'])
        rows[0]['result']['passed'] = False
        self.assertFalse(controls.aggregate(m, rows)['analog_source_controls_passed'])
        with self.assertRaises(ValueError): controls.aggregate(m, rows[:-1])
        with self.assertRaises(ValueError): controls.aggregate(m, rows[:-1] + [rows[0]])

    def test_campaign_profile_restores_after_rejecting_existing_output(self):
        original = controls.expansion.screen.original; previous = original.dc, original.NAMESPACE, original.admission
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root / 'manifest.json').write_text('{}'); (root / 'state.json').write_text('{}')
            with patch.object(controls, 'bound', return_value=dict(identity=dict(parent='source'))), patch.object(controls, 'command') as command:
                with self.assertRaisesRegex(ValueError, 'no retry'): controls.run(root)
                command.assert_not_called()
        self.assertEqual((original.dc, original.NAMESPACE, original.admission), previous)
