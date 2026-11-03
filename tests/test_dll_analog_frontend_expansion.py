import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import expand_dll_analog_frontend as expansion


class AnalogSourceExpansion(unittest.TestCase):
    def setUp(self):
        self.requirements = json.loads((expansion.ROOT / 'requirements.json').read_text())
        self.tasks = expansion.tasks(self.requirements, 'tail140_w20')
        self.manifest = dict(identity=dict(variant='tail140_w20'), tasks=self.tasks)

    def rows(self):
        return [dict(task=t['id'], variant=t['variant'], spec=t['spec'], error=None,
            result=dict(passed=True, native_phase=dict(phase=dict(
                filtered_area_difference_v=t['spec']['offset_ps'] / 1000), mean_power_w=.005))) for t in self.tasks]

    def test_full_fixed_supply_coverage_and_unique_tasks(self):
        self.assertEqual(len(self.tasks), 1215)
        self.assertEqual(len({t['id'] for t in self.tasks}), 1215)
        specs = [t['spec'] for t in self.tasks]
        self.assertEqual({(s['process'], s['temperature']) for s in specs},
            {(p, t) for p in ('tt', 'ff', 'ss', 'fs', 'sf') for t in (0, 25, 40)})
        self.assertEqual({s['mhz'] for s in specs}, {390, 400, 410})
        self.assertEqual({(s['reference_slew_ps'], s['feedback_slew_ps']) for s in specs},
            {(100, 100), (20, 200), (200, 20)})
        changed = dict(self.requirements, supply_sweep=True)
        with self.assertRaises(ValueError): expansion.tasks(changed, 'tail140_w20')

    def test_no_survivor_or_incomplete_screen_cannot_create_artifact(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'build/diagnostics' / expansion.screen.NAMESPACE / 'parent'
            parent.mkdir(parents=True)
            for report in [dict(ranked_survivors=[], analog_source_screen_passed=False),
                           dict(ranked_survivors=['tail140_w20'], analog_source_screen_passed=False)]:
                with patch.object(expansion, 'ROOT', root), patch.object(expansion.screen, 'verify', return_value=report), \
                     patch.object(expansion.screen, 'bound', return_value={}):
                    with self.assertRaises(ValueError): expansion.prepare(parent)
                self.assertFalse((root / 'build/diagnostics' / expansion.NAMESPACE).exists())
            with patch.object(expansion, 'ROOT', root), patch.object(expansion.screen, 'verify', side_effect=ValueError('incomplete')):
                with self.assertRaises(ValueError): expansion.prepare(parent)

    def test_default_winner_and_explicit_selection_require_full_survival(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); parent = root / 'build/diagnostics' / expansion.screen.NAMESPACE / 'parent'
            parent.mkdir(parents=True)
            report = dict(ranked_survivors=['tail140_w20', 'tail280_w40'], analog_source_screen_passed=True)
            with patch.object(expansion, 'ROOT', root), patch.object(expansion.screen, 'verify', return_value=report), \
                 patch.object(expansion.screen, 'bound', return_value={}):
                self.assertEqual(expansion.admission(parent)[2], 'tail140_w20')
                self.assertEqual(expansion.admission(parent, 'tail280_w40')[2], 'tail280_w40')
                with self.assertRaises(ValueError): expansion.admission(parent, 'tail140_w40')

    def test_aggregate_never_grants_physical_or_phy_admission(self):
        report = expansion.aggregate(self.manifest, self.rows())
        self.assertTrue(report['analog_source_expansion_passed'])
        self.assertEqual(len(report['checks']), 135)
        self.assertEqual(report['estimated_zero_offset_max_abs_ps'], 0)
        self.assertFalse(report['physical_admission']); self.assertFalse(report['qualified_phy'])

    def test_missing_duplicate_foreign_corner_and_manifest_coverage_rejected(self):
        rows = self.rows()
        for changed in [rows[:-1], rows[:-1] + [rows[0]]]:
            with self.assertRaises(ValueError): expansion.aggregate(self.manifest, changed)
        changed = copy.deepcopy(rows); changed[0]['spec']['temperature'] = 85
        with self.assertRaises(ValueError): expansion.aggregate(self.manifest, changed)
        manifest = dict(self.manifest, tasks=self.tasks[:-1])
        with self.assertRaises(ValueError): expansion.aggregate(manifest, rows)

    def test_reference_stress_transport_and_numerical_failures_cannot_be_hidden_by_balance(self):
        for field in ('reference', 'stress', 'clock_transport', 'numerical'):
            rows = self.rows()
            if field == 'numerical': rows[0].update(error='incomplete trace', result=None)
            else: rows[0]['result'].update(passed=False, failed_gate=field)
            self.assertFalse(expansion.aggregate(self.manifest, rows)['analog_source_expansion_passed'])

    def test_one_bad_curve_rejects_whole_expansion(self):
        for offset, value in [(-20, .001), (300, -.5), (0, float('nan'))]:
            rows = self.rows()
            row = next(r for r in rows if r['spec']['offset_ps'] == offset)
            row['result']['native_phase']['phase']['filtered_area_difference_v'] = value
            self.assertFalse(expansion.aggregate(self.manifest, rows)['analog_source_expansion_passed'])

    def test_expansion_uses_single_campaign_profile_and_restores_on_error(self):
        original = expansion.screen.original
        previous = original.dc, original.NAMESPACE, original.admission
        with patch.object(expansion, 'bound', side_effect=ValueError('bad context')):
            with self.assertRaises(ValueError): expansion.run(Path('artifact'))
        self.assertEqual((original.dc, original.NAMESPACE, original.admission), previous)
        with self.assertRaises(ValueError): expansion.measure(Path('folder'), {})

    def test_fixture_changes_only_corner_and_retains_analog_engine_and_gate_map(self):
        task = self.tasks[0]
        task = dict(task, spec=dict(task['spec'], process='ff', temperature=25))
        with tempfile.TemporaryDirectory() as name:
            out = Path(name); (out / 'tail140_w20.spice').write_text('same full native model')
            with patch.object(expansion.screen.original, 'context', return_value=(['analog'], {'gate': 'actual'},
                    '.lib "pdk" ss\n.options device temp=40\n')), \
                 patch.object(expansion.screen.original, 'fixture', return_value=('deck', {'gate': 'actual'})) as fixture:
                self.assertEqual(expansion.fixture(task, {}, out), ('deck', {'gate': 'actual'}))
                args = fixture.call_args.args
                self.assertEqual(args[:3], (task, ['analog'], {'gate': 'actual'}))
                self.assertEqual(args[3], '.lib "pdk" ff\n.options device temp=25\n')
                self.assertEqual(args[5], 'same full native model')
