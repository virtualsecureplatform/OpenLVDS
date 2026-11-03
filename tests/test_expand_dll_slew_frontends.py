from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import expand_dll_slew_frontends as expansion


class ExpandedFrontendScreen(unittest.TestCase):
    def setUp(self):
        self.req = json.loads((expansion.ROOT / 'requirements.json').read_text())
        self.variant = expansion.screen.cal.CANDIDATES[0]

    def evidence(self):
        tasks = expansion.tasks(self.req, [self.variant])
        m = dict(identity=dict(variants=[self.variant], footprint_um2={self.variant: 15}, scope='test'), tasks=tasks)
        rows = [dict(task=t['id'], variant=t['variant'], spec=t['spec'], error=None,
                     result=dict(passed=True, mean_power_w=.001,
                                 phase={'filtered_area_difference_v': (t['spec']['offset_ps'] - (12 if t['spec']['process'] == 'fs' and t['spec']['temperature'] == 25 else 1)) * .0007})) for t in tasks]
        return m, rows

    def test_matrix_only_expands_admitted_variants_and_has_unique_ids(self):
        tasks = expansion.tasks(self.req, [self.variant])
        self.assertEqual(len(tasks), 1215)
        self.assertEqual(len({t['id'] for t in tasks}), 1215)
        for variants in ([], ['buf_4'], [self.variant, self.variant]):
            with self.assertRaises(ValueError): expansion.tasks(self.req, variants)

    def test_worst_pvt_is_measured_across_frequency_and_slew(self):
        m, rows = self.evidence(); result = expansion.aggregate(m, rows)
        self.assertEqual(result['ranked_survivors'], [self.variant])
        self.assertEqual(result['candidates'][0]['worst_screened_pvt'], ['fs', 25])
        self.assertAlmostEqual(result['candidates'][0]['estimated_zero_offset_max_abs_ps'], 12)
        self.assertFalse(result['physical_admission']); self.assertFalse(result['qualified_phy'])

    def test_false_bad_unbalanced_nonmonotonic_or_numerical_failure_holds(self):
        m, good = self.evidence()
        for mutation in ('false_bad', 'balance', 'monotonic', 'numerical'):
            rows = deepcopy(good)
            if mutation == 'false_bad': rows[0]['result']['passed'] = False
            if mutation == 'numerical': rows[0]['error'] = 'incomplete'; rows[0]['result'] = None
            if mutation == 'balance':
                for r in rows: r['result']['phase']['filtered_area_difference_v'] += .03
            if mutation == 'monotonic': rows[0]['result']['phase']['filtered_area_difference_v'] = .5
            with self.subTest(mutation=mutation):
                self.assertEqual(expansion.aggregate(m, rows)['ranked_survivors'], [])

    def test_missing_duplicate_or_changed_task_metadata_rejected(self):
        m, rows = self.evidence()
        for bad in (rows[:-1], rows + [rows[0]], [dict(rows[0], spec={})] + rows[1:]):
            with self.assertRaises(ValueError): expansion.aggregate(m, bad)

    def test_corner_prefix_changes_only_process_and_temperature(self):
        text = 'fixture\n.lib "/pinned/pdk.spice" ss\n.options device temp=40\nVA VDDIO 0 3.3\nVD VDDD 0 1.8\n'
        changed = expansion.corner_prefix(text, 'fs', 25)
        self.assertEqual(changed.replace(' fs\n', ' ss\n').replace('temp=25', 'temp=40'), text)
        with self.assertRaises(ValueError): expansion.corner_prefix('no pinned include', 'fs', 25)

    def test_no_survivor_and_partial_outputs_never_dispatch_spice(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            with patch.object(expansion.screen, 'verify', return_value={'ranked_survivors': []}):
                with self.assertRaisesRegex(ValueError, 'analog fallback'): expansion.survivor_gate(p)
            (p / 'manifest.json').write_text('{}'); (p / 'state.json').write_text('{}')
            with patch.object(expansion, 'bound', return_value={'tasks': []}), patch.object(expansion, 'lease') as lease:
                with self.assertRaisesRegex(ValueError, 'no retry'): expansion.run(p)
                lease.assert_not_called()
